"""Validated local configuration and scene definitions. No UI or network I/O."""
from dataclasses import asdict, dataclass, field
from ipaddress import IPv4Address


def integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label}: debe ser un entero entre {minimum} y {maximum}.")
    return value


def name_text(value, label="Nombre"):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 40:
        raise ValueError(f"{label}: usá entre 1 y 40 caracteres.")
    return value.strip()


@dataclass(frozen=True)
class BulbConfig:
    id: str
    name: str
    ip: str

    def __post_init__(self):
        if self.id not in ("bulb1", "bulb2"):
            raise ValueError("Identificador de bombilla inválido.")
        object.__setattr__(self, "name", name_text(self.name))
        try:
            address = IPv4Address(self.ip)
        except (ValueError, TypeError) as error:
            raise ValueError("Ingresá una dirección IPv4 válida.") from error
        if address.is_unspecified or address.is_multicast or int(address) == 0xFFFFFFFF:
            raise ValueError("Ingresá una IP individual, no una dirección de difusión.")


@dataclass(frozen=True)
class LightSetting:
    power: bool = True
    brightness: int = 70
    rgb: tuple[int, int, int] | None = (145, 45, 255)
    kelvin: int | None = None
    warm_white: int | None = None

    def __post_init__(self):
        if type(self.power) is not bool:
            raise ValueError("Encendido debe ser verdadero o falso.")
        integer(self.brightness, 5, 100, "Brillo")
        if self.rgb is not None:
            if not isinstance(self.rgb, (list, tuple)) or len(self.rgb) != 3:
                raise ValueError("RGB debe contener tres canales.")
            for channel in self.rgb:
                integer(channel, 0, 255, "Canal RGB")
            object.__setattr__(self, "rgb", tuple(self.rgb))
        if self.kelvin is not None:
            integer(self.kelvin, 2200, 6500, "Temperatura")
        if (self.rgb is None) == (self.kelvin is None):
            raise ValueError("Elegí RGB o temperatura de blanco.")
        if self.warm_white is not None:
            integer(self.warm_white, 0, 255, "LED blanco")
            if self.rgb is None:
                raise ValueError("El canal blanco solo se usa con una captura RGB.")


@dataclass(frozen=True)
class Scene:
    name: str
    lights: dict[str, LightSetting]

    def __post_init__(self):
        object.__setattr__(self, "name", name_text(self.name, "Escena"))
        if set(self.lights) != {"bulb1", "bulb2"}:
            raise ValueError("Cada escena debe configurar las dos bombillas.")
        if not all(isinstance(value, LightSetting) for value in self.lights.values()):
            raise ValueError("Configuración de escena inválida.")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        return cls(value["name"], {key: LightSetting(**setting)
                                   for key, setting in value["lights"].items()})


def builtin_scenes():
    def pair(name, first, second, level):
        return Scene(name, {"bulb1": LightSetting(brightness=level, rgb=first),
                            "bulb2": LightSetting(brightness=level, rgb=second)})
    def white(name, kelvin, level):
        return Scene(name, {key: LightSetting(brightness=level, rgb=None, kelvin=kelvin)
                            for key in ("bulb1", "bulb2")})
    return {
        "Gaming": pair("Gaming", (145, 45, 255), (0, 210, 255), 70),
        "Streaming": pair("Streaming", (255, 45, 140), (40, 120, 255), 80),
        "Relax": white("Relax", 2700, 45),
        "Estudio": white("Estudio", 4000, 100),
        "Noche": pair("Noche", (35, 35, 160), (80, 30, 110), 15),
    }


@dataclass
class AppConfig:
    # Public defaults are documentation addresses; real devices live in data/config.json.
    bulbs: list[BulbConfig] = field(default_factory=lambda: [
        BulbConfig("bulb1", "Luz 1", "192.0.2.10"),
        BulbConfig("bulb2", "Luz 2", "192.0.2.11"),
    ])
    startup_scene: str | None = None
    accent: str = "Violeta"
    palette: str = "Medianoche"
    scale: int = 100

    def __post_init__(self):
        if len(self.bulbs) != 2 or {bulb.id for bulb in self.bulbs} != {"bulb1", "bulb2"}:
            raise ValueError("Se necesitan las dos bombillas con identificadores únicos.")
        if len({bulb.ip for bulb in self.bulbs}) != 2:
            raise ValueError("Las bombillas deben tener IP diferentes.")
        if self.startup_scene is not None:
            name_text(self.startup_scene, "Escena de inicio")
        if self.accent not in ("Violeta", "Cian", "Magenta"):
            raise ValueError("Acento inválido.")
        if self.palette not in ("Medianoche", "Grafito") or self.scale not in (100, 110, 125):
            raise ValueError("Preferencia de apariencia inválida.")

    def to_dict(self):
        return {"version": 1, **asdict(self)}

    @classmethod
    def from_dict(cls, value):
        data = dict(value)
        if data.pop("version", 1) != 1:
            raise ValueError("Versión de configuración no compatible.")
        data["bulbs"] = [BulbConfig(**bulb) for bulb in data["bulbs"]]
        return cls(**data)
