from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Destination:
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class NavigationStep:
    text: str
    latitude: float
    longitude: float
    distance_m: float


@dataclass(frozen=True)
class RoutePlan:
    destination: Destination
    distance_m: float
    time_s: float
    steps: list[NavigationStep]


MCMASTER_DESTINATIONS: dict[str, Destination] = {
    "Kenneth Taylor Hall": Destination("Kenneth Taylor Hall", 43.26394, -79.91917),
    "Engineering Technology Building": Destination("Engineering Technology Building", 43.25848, -79.92012),
    "McMaster University Student Centre": Destination("McMaster University Student Centre", 43.26264, -79.91715),
    "McMaster University Medical Centre": Destination("McMaster University Medical Centre", 43.25954, -79.91925),
    "H. G. Thode Library": Destination("H. G. Thode Library", 43.26082, -79.92205),
    "E. T. Clarke Centre": Destination("E. T. Clarke Centre", 43.26019, -79.92133),
}


def list_destination_names() -> list[str]:
    return sorted(MCMASTER_DESTINATIONS)


def get_destination(name: str) -> Optional[Destination]:
    return MCMASTER_DESTINATIONS.get(name)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius_m * c


class GraphHopperClient:
    def __init__(self, base_url: str, profile: str = "foot"):
        self.base_url = base_url.rstrip("/")
        self.profile = profile

    def route(
        self,
        start_lat: float,
        start_lon: float,
        destination: Destination,
    ) -> RoutePlan:
        params = urllib.parse.urlencode(
            [
                ("point", f"{start_lat},{start_lon}"),
                ("point", f"{destination.latitude},{destination.longitude}"),
                ("profile", self.profile),
                ("locale", "en"),
                ("instructions", "true"),
                ("calc_points", "true"),
                ("points_encoded", "false"),
            ],
            doseq=True,
        )
        url = f"{self.base_url}/route?{params}"
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        paths = payload.get("paths") or []
        if not paths:
            raise RuntimeError("GraphHopper returned no paths.")

        path = paths[0]
        coordinates = ((path.get("points") or {}).get("coordinates")) or []
        instructions = path.get("instructions") or []
        if not coordinates or not instructions:
            raise RuntimeError("GraphHopper route response missing coordinates or instructions.")

        steps: list[NavigationStep] = []
        for instruction in instructions:
            interval = instruction.get("interval") or [0, 0]
            coord_index = min(max(int(interval[-1]), 0), len(coordinates) - 1)
            lon, lat = coordinates[coord_index]
            text = str(instruction.get("text") or "Continue.")
            distance_m = float(instruction.get("distance") or 0.0)
            steps.append(
                NavigationStep(
                    text=text,
                    latitude=float(lat),
                    longitude=float(lon),
                    distance_m=distance_m,
                )
            )

        return RoutePlan(
            destination=destination,
            distance_m=float(path.get("distance") or 0.0),
            time_s=float(path.get("time") or 0.0) / 1000.0,
            steps=steps,
        )


class NavigationSession:
    def __init__(
        self,
        route_plan: RoutePlan,
        step_trigger_radius_m: float = 15.0,
        arrival_radius_m: float = 20.0,
    ):
        self.route_plan = route_plan
        self.step_trigger_radius_m = step_trigger_radius_m
        self.arrival_radius_m = arrival_radius_m
        self.active = bool(route_plan.steps)
        self.current_step_index = 0
        self.last_step_index_announced = -1
        self.arrived = False

    def start_message(self) -> str:
        minutes = max(self.route_plan.time_s / 60.0, 1.0)
        first = self.current_instruction()
        if first:
            return (
                f"Navigation to {self.route_plan.destination.name}. "
                f"{self.route_plan.distance_m:.0f} meters, about {minutes:.0f} minutes. "
                f"{first}"
            )
        return f"Navigation to {self.route_plan.destination.name} started."

    def current_instruction(self) -> Optional[str]:
        if not self.active or self.current_step_index >= len(self.route_plan.steps):
            return None
        return self.route_plan.steps[self.current_step_index].text

    def update_position(self, latitude: float, longitude: float) -> Optional[str]:
        if not self.active or self.arrived:
            return None

        destination = self.route_plan.destination
        if _haversine_m(latitude, longitude, destination.latitude, destination.longitude) <= self.arrival_radius_m:
            self.arrived = True
            self.active = False
            return f"Arrived at {destination.name}."

        while self.current_step_index < len(self.route_plan.steps):
            step = self.route_plan.steps[self.current_step_index]
            distance_to_step = _haversine_m(latitude, longitude, step.latitude, step.longitude)
            if distance_to_step > self.step_trigger_radius_m:
                break
            self.current_step_index += 1

        if self.current_step_index >= len(self.route_plan.steps):
            return None

        if self.current_step_index != self.last_step_index_announced:
            self.last_step_index_announced = self.current_step_index
            return self.route_plan.steps[self.current_step_index].text

        return None
