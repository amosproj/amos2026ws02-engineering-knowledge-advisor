import pytest
from fakes import MemoryRecordStore
from record_store_checks import CHECK_IDS, CHECKS, IDENTITY_PROPERTY_NAMES, Check

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("check", CHECKS, ids=CHECK_IDS)
async def test_record_store_contract_in_memory(check: Check):
    await check(MemoryRecordStore(IDENTITY_PROPERTY_NAMES))
