import asyncio
import unittest
from unittest.mock import AsyncMock

from pywizlight import PilotParser

from wiz_controller.lighting import BulbState, LightingService, UnconfirmedError
from wiz_controller.models import LightSetting


class LightingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.light = type("FakeLight", (), {})()
        self.light.turn_on = AsyncMock()
        self.light.turn_off = AsyncMock()
        self.light.async_close = AsyncMock()
        self.light.updateState = AsyncMock(return_value=PilotParser({
            "state": True, "dimming": 70, "r": 121, "g": 0, "b": 255, "w": 73}))
        self.service = LightingService(lambda ip: self.light, timeout=0.05, settle_delay=0)

    async def test_rgb_command_and_confirmed_readback(self):
        state = await self.service.execute("192.0.2.10", "color", rgb=(145, 45, 255), brightness=70)
        builder = self.light.turn_on.call_args.args[0]
        payload = builder.set_pilot_message()["params"]
        # pywizlight converts the requested RGB into native RGB + white channels.
        self.assertEqual((payload["r"], payload["g"], payload["b"], payload["w"]), (121, 0, 255, 73))
        self.assertAlmostEqual(payload["dimming"], 70, delta=1)
        self.assertEqual(state.brightness, 70)
        self.light.async_close.assert_awaited_once()

    async def test_on_preserves_bulb_settings(self):
        await self.service.execute("ip", "on")
        payload = self.light.turn_on.call_args.args[0].set_pilot_message()["params"]
        self.assertNotIn("dimming", payload)
        self.assertNotIn("r", payload)

    async def test_off_requires_confirmation(self):
        self.light.updateState.return_value = PilotParser({"state": False})
        state = await self.service.execute("ip", "off")
        self.assertFalse(state.power)
        self.light.turn_off.assert_awaited_once()

    async def test_brightness_keeps_original_minimum(self):
        self.light.updateState.return_value = PilotParser({"state": True, "dimming": 5})
        await self.service.execute("ip", "brightness", brightness=5)
        params = self.light.turn_on.call_args.args[0].set_pilot_message()["params"]
        self.assertEqual(params["dimming"], 5)

    async def test_white_scene_uses_colortemp(self):
        self.light.updateState.return_value = PilotParser({"state": True, "dimming": 45, "temp": 2700, "r": 0, "g": 0, "b": 0})
        setting = LightSetting(True, 45, None, 2700)
        await self.service.execute("ip", "scene", setting=setting)
        params = self.light.turn_on.call_args.args[0].set_pilot_message()["params"]
        self.assertEqual(params["temp"], 2700)

    async def test_capture_replays_native_rgb_white_without_second_conversion(self):
        state = await self.service.execute("ip")
        await self.service.execute("ip", "scene", setting=state.as_setting())
        params = self.light.turn_on.call_args.args[0].set_pilot_message()["params"]
        self.assertEqual((params["r"], params["g"], params["b"], params["w"]), (121, 0, 255, 73))

    async def test_missing_white_channel_does_not_confirm_rgb_mix(self):
        self.light.updateState.return_value = PilotParser({"state": True, "dimming": 70, "r": 121, "g": 0, "b": 255})
        with self.assertRaises(UnconfirmedError):
            await self.service.execute("ip", "color", rgb=(145, 45, 255))

    async def test_scene_can_turn_one_channel_off(self):
        self.light.updateState.return_value = PilotParser({"state": False})
        await self.service.execute("ip", "scene", setting=LightSetting(power=False))
        self.light.turn_off.assert_awaited_once()
        self.light.turn_on.assert_not_awaited()

    async def test_newer_parser_list_is_supported(self):
        self.light.updateState.return_value = [self.light.updateState.return_value]
        self.assertTrue((await self.service.execute("ip")).power)

    async def test_no_response_is_not_success(self):
        self.light.updateState.return_value = None
        with self.assertRaises(ValueError):
            await self.service.execute("ip", "on")
        self.light.async_close.assert_awaited_once()

    async def test_mismatch_is_reported_with_actual_state(self):
        with self.assertRaises(UnconfirmedError) as error:
            await self.service.execute("ip", "off")
        self.assertTrue(error.exception.state.power)
        self.assertEqual(self.light.updateState.await_count, 2)
        self.light.async_close.assert_awaited_once()

    async def test_delayed_firmware_confirmation(self):
        self.light.updateState.side_effect = [PilotParser({"state": True}), PilotParser({"state": False})]
        self.assertFalse((await self.service.execute("ip", "off")).power)

    async def test_timeout_closes_transport(self):
        async def slow(*args):
            await asyncio.sleep(1)
        self.light.turn_on.side_effect = slow
        with self.assertRaises(TimeoutError):
            await self.service.execute("ip", "on")
        self.light.async_close.assert_awaited_once()

    async def test_cancel_closes_transport(self):
        async def slow(*args):
            await asyncio.sleep(1)
        self.light.updateState.side_effect = slow
        task = asyncio.create_task(self.service.execute("ip"))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.light.async_close.assert_awaited_once()

    async def test_network_error_closes_transport(self):
        self.light.turn_on.side_effect = OSError("unreachable")
        with self.assertRaises(OSError):
            await self.service.execute("ip", "on")
        self.light.async_close.assert_awaited_once()

    async def test_unknown_action_is_rejected(self):
        with self.assertRaises(ValueError):
            await self.service.execute("ip", "unknown")
        self.light.turn_on.assert_not_awaited()

    def test_capture_requires_real_color_and_brightness(self):
        with self.assertRaises(ValueError):
            BulbState(True, None, None, None).as_setting()
        setting = BulbState(True, 45, None, 2700).as_setting()
        self.assertEqual(setting.kelvin, 2700)
