"""测试里以人的名义写记忆：每个治理 store 领一次人工入口，之后复用。"""

import weakref

from one_memory.memory_governance import MemoryGovernanceStore, PersonWrites

_doors: weakref.WeakKeyDictionary[MemoryGovernanceStore, PersonWrites] = weakref.WeakKeyDictionary()


def as_person(store: MemoryGovernanceStore | PersonWrites) -> PersonWrites:
    """A store Core opened has already handed its door over: pass `app.state.person_writes`."""
    if isinstance(store, PersonWrites):
        return store
    door = _doors.get(store)
    if door is None:
        door = _doors[store] = store.claim_person_writes("user")
    return door
