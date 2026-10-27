"""Serializable OTA state. Production state always lives in Firebase RTDB."""
import asyncio
import copy


class MemoryStore:
    """Explicitly injected test backend; never selected by production startup."""

    def __init__(self):
        self._state = {}
        self._lock = asyncio.Lock()

    async def read(self, path=''):
        async with self._lock:
            value = self._state
            for part in path.strip('/').split('/') if path else []:
                value = value.get(part, {})
            return copy.deepcopy(value)

    async def transaction(self, operation):
        async with self._lock:
            state = copy.deepcopy(self._state)
            result = operation(state)
            self._state = state
            return copy.deepcopy(result)


class FirebaseStore:
    def __init__(self, reference):
        self.reference = reference

    async def read(self, path=''):
        reference = self.reference.child(path) if path else self.reference
        return await asyncio.to_thread(reference.get) or {}

    async def transaction(self, operation):
        result = None

        def update(current):
            nonlocal result
            state = copy.deepcopy(current or {})
            result = operation(state)
            return state

        # shortcut: one namespace transaction serializes the pilot, shard with an
        # explicit campaign-revocation fence before scaling beyond pilot traffic.
        await asyncio.to_thread(self.reference.transaction, update)
        return copy.deepcopy(result)
