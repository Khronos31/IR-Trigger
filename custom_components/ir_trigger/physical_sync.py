"""Pure helpers for opt-in physical IR controller state synchronization."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping

SYNC_ACCEPTED = "accepted"
SYNC_DUPLICATE = "duplicate"
SYNC_ECHO = "echo"

_LIGHT_ACTIONS = frozenset({"on", "off", "toggle", "ignore"})


def validate_receiver_scope(
    enabled: bool,
    receivers: str | Iterable[str] | None,
    device_id: str,
) -> frozenset[str]:
    """Normalize receiver scope and require it for opted-in devices."""
    if receivers is None:
        normalized = frozenset()
    elif isinstance(receivers, str):
        normalized = frozenset({receivers}) if receivers else frozenset()
    else:
        try:
            normalized = frozenset(receivers)
        except TypeError as err:
            raise ValueError(f"{device_id}: receiver must be a string or list") from err
        if any(not isinstance(receiver, str) or not receiver for receiver in normalized):
            raise ValueError(f"{device_id}: receiver entries must be nonempty strings")
    if enabled and not normalized:
        raise ValueError(
            f"{device_id}: sync_physical_controller requires receiver scoping"
        )
    return normalized


def build_light_sync_actions(
    buttons: Mapping[str, str],
    mapping: Mapping[str, str],
    explicit_actions: Mapping[str, str],
) -> dict[str, str]:
    """Build a code-to-state-action map from standard and explicit mappings."""
    button_actions: dict[str, str] = {}
    turn_on = mapping.get("turn_on")
    turn_off = mapping.get("turn_off")
    if turn_on and turn_off and turn_on == turn_off:
        button_actions[turn_on] = "toggle"
    else:
        if turn_on:
            button_actions[turn_on] = "on"
        if turn_off:
            button_actions[turn_off] = "off"

    for button, action in explicit_actions.items():
        if action not in _LIGHT_ACTIONS:
            raise ValueError(
                f"{button}: invalid light sync action {action!r}; "
                "expected on, off, toggle, or ignore"
            )
        button_actions[button] = action

    code_actions: dict[str, str] = {}
    for button, action in button_actions.items():
        if button not in buttons:
            raise ValueError(f"state_sync references unknown light button {button!r}")
        if action == "ignore":
            continue
        code = buttons[button]
        previous = code_actions.get(code)
        if previous is not None and previous != action:
            raise ValueError(
                f"conflicting light sync actions for code {code!r}: "
                f"{previous!r} and {action!r}"
            )
        code_actions[code] = action
    return code_actions


def apply_light_sync_action(current: bool, action: str) -> bool | None:
    """Return the light state represented by a physical remote action."""
    if action == "on":
        return True
    if action == "off":
        return False
    if action == "toggle":
        return not current
    return None


class PhysicalSyncGuard:
    """Correlate local transmissions and deduplicate received controller frames."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        echo_window: float = 1.0,
        duplicate_window: float = 0.3,
    ) -> None:
        self._clock = clock
        self._echo_window = echo_window
        self._duplicate_window = duplicate_window
        self._transmissions: deque[tuple[float, str, frozenset[str]]] = deque()
        self._received: dict[tuple[str, str], float] = {}

    def record_transmission(self, code: str, local_receivers: Iterable[str]) -> None:
        """Record a code immediately before sending it to a transmitter."""
        receivers = frozenset(local_receivers)
        if receivers:
            self._transmissions.append((self._clock(), code, receivers))

    def classify_received(self, receiver: str, code: str) -> str:
        """Classify a frame for state sync without affecting event/routing delivery."""
        now = self._clock()
        while self._transmissions and now - self._transmissions[0][0] > self._echo_window:
            self._transmissions.popleft()
        if any(
            recorded_code == code and receiver in local_receivers
            for _, recorded_code, local_receivers in self._transmissions
        ):
            return SYNC_ECHO

        key = (receiver, code)
        previous = self._received.get(key)
        self._received[key] = now
        if previous is not None and now - previous <= self._duplicate_window:
            return SYNC_DUPLICATE

        cutoff = now - max(self._duplicate_window, 5.0)
        self._received = {
            item: timestamp
            for item, timestamp in self._received.items()
            if timestamp >= cutoff
        }
        return SYNC_ACCEPTED


class PhysicalSyncTrackingTransmitter:
    """Record outgoing codes before delegating to the real transmitter."""

    def __init__(self, transmitter, sync_guard, local_receivers) -> None:
        self._transmitter = transmitter
        self._sync_guard = sync_guard
        self._local_receivers = tuple(local_receivers)

    async def async_send(self, code: str):
        self._sync_guard.record_transmission(code, self._local_receivers)
        return await self._transmitter.async_send(code)
