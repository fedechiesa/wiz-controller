"""Original pywizlight commands, bounded by timeouts and verified by a fresh read."""
import asyncio
from dataclasses import dataclass

from pywizlight import PilotBuilder, wizlight

from .models import LightSetting


@dataclass(frozen=True)
class BulbState:
    power: bool
    brightness: int | None
    rgb: tuple[int, int, int] | None
    kelvin: int | None
    warm_white: int | None = None

    def as_setting(self):
        if self.brightness is None or (self.rgb is None and self.kelvin is None):
            raise ValueError("La bombilla no informó brillo/color suficientes para guardar una escena.")
        return LightSetting(self.power, max(5, self.brightness), self.rgb,
                            self.kelvin if self.rgb is None else None,
                            self.warm_white if self.rgb is not None else None)


class UnconfirmedError(Exception):
    """The bulb replied, but its reported state differs from the request."""

    def __init__(self, state):
        super().__init__("La bombilla respondió, pero no confirmó el ajuste solicitado.")
        self.state = state


class LightingService:
    def __init__(self, factory=wizlight, timeout=7, settle_delay=0.15):
        self.factory = factory
        self.timeout = timeout
        self.settle_delay = settle_delay

    async def _read(self, light):
        result = await asyncio.wait_for(light.updateState(), self.timeout)
        # pywizlight 0.6.6 distributions expose either a parser or a list of parsers.
        parser = result[0] if isinstance(result, (list, tuple)) and result else result
        if parser is None or not hasattr(parser, "get_state") or parser.get_state() is None:
            raise ValueError("La bombilla no devolvió un estado válido.")
        rgb = parser.get_rgb()
        rgb = tuple(rgb) if rgb is not None and all(c is not None for c in rgb) else None
        raw_level = parser.get_brightness()
        kelvin = parser.get_colortemp()
        kelvin = kelvin if kelvin and kelvin > 0 else None
        if kelvin is not None:
            rgb = None
        return BulbState(parser.get_state(), round(raw_level * 100 / 255) if raw_level is not None else None,
                         rgb, kelvin, parser.get_warm_white())

    async def execute(self, ip, action="refresh", *, rgb=None, brightness=70, setting=None):
        if action not in {"refresh", "on", "off", "brightness", "color", "scene"}:
            raise ValueError("Acción de iluminación desconocida.")
        if action in {"color", "scene", "brightness"}:
            if action == "scene" and not isinstance(setting, LightSetting):
                raise ValueError("La escena requiere una configuración válida.")
            if action != "scene":
                LightSetting(brightness=brightness, rgb=rgb if action == "color" else (0, 0, 0))
        light = self.factory(ip)
        try:
            expected = {}
            if action != "refresh":
                if action == "off" or (action == "scene" and not setting.power):
                    command = light.turn_off()
                else:
                    kwargs = {}
                    if action in {"color", "brightness"}:
                        kwargs["brightness"] = max(10, min(255, round(brightness * 255 / 100)))
                    if action == "color":
                        kwargs["rgb"] = rgb
                    if action == "scene":
                        kwargs = {"brightness": max(10, round(setting.brightness * 255 / 100))}
                        if setting.warm_white is not None:
                            kwargs["rgbw"] = (*setting.rgb, setting.warm_white)
                        else:
                            kwargs["rgb" if setting.rgb is not None else "colortemp"] = setting.rgb or setting.kelvin
                    builder = PilotBuilder(**kwargs)
                    expected = builder.set_pilot_message()["params"]
                    command = light.turn_on(builder)
                await asyncio.wait_for(command, self.timeout)
                await asyncio.sleep(self.settle_delay)
            state = await self._read(light)
            if not self._matches(state, action, brightness, setting, expected):
                await asyncio.sleep(self.settle_delay)
                state = await self._read(light)
                if not self._matches(state, action, brightness, setting, expected):
                    raise UnconfirmedError(state)
            return state
        finally:
            await light.async_close()

    @staticmethod
    def _matches(state, action, brightness, setting, expected):
        if action == "refresh":
            return True
        desired_power = setting.power if action == "scene" else action != "off"
        if state.power != desired_power:
            return False
        if not desired_power or action == "on":
            return True
        level = setting.brightness if action == "scene" else brightness
        if state.brightness is None or abs(state.brightness - level) > 2:
            return False
        if "r" in expected:
            color = tuple(expected[key] for key in ("r", "g", "b"))
            if state.rgb is None or any(abs(a - b) > 8 for a, b in zip(color, state.rgb)):
                return False
            if "w" in expected and abs(expected["w"] - (state.warm_white or 0)) > 8:
                return False
        if action == "scene" and setting.kelvin is not None:
            return state.kelvin is not None and abs(state.kelvin - setting.kelvin) <= 100
        return True
