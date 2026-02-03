"""Script to backfill call durations from Telnyx API."""

import asyncio
import logging
from sqlalchemy import select
from app.persistence.database import AsyncSessionLocal
from app.persistence.models.call import Call
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.infrastructure.telephony.telnyx_provider import TelnyxAIService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def backfill():
    async with AsyncSessionLocal() as db:
        # Find calls with missing duration data
        query = select(Call).where(
            (Call.duration == 0) | (Call.duration.is_(None)),
            (Call.ended_at.is_(None)) | (Call.ended_at == Call.started_at),
        ).order_by(Call.created_at.desc()).limit(200)

        result = await db.execute(query)
        calls = result.scalars().all()

        print(f"Found {len(calls)} calls with missing duration data")

        # Get unique tenant IDs for API key lookup
        tenant_ids = set(call.tenant_id for call in calls)

        # Fetch Telnyx API keys for each tenant
        tenant_api_keys = {}
        for tid in tenant_ids:
            config_result = await db.execute(
                select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tid)
            )
            config = config_result.scalar_one_or_none()
            if config and config.telnyx_api_key:
                tenant_api_keys[tid] = config.telnyx_api_key
                print(f"Found API key for tenant {tid}")

        updated = 0
        failed = 0

        for call in calls:
            api_key = tenant_api_keys.get(call.tenant_id)
            if not api_key:
                print(f"Call {call.id}: No API key for tenant {call.tenant_id}")
                failed += 1
                continue

            try:
                telnyx_ai = TelnyxAIService(api_key)
                conv_data = await telnyx_ai.find_conversation_by_call_control_id(call.call_sid)

                if conv_data:
                    conv_created = conv_data.get("created_at")
                    conv_updated = conv_data.get("updated_at")
                    print(f"  Conv timestamps: created={conv_created}, updated={conv_updated}")

                    if conv_created and conv_updated and conv_created != conv_updated:
                        from dateutil import parser as date_parser
                        start_dt = date_parser.parse(str(conv_created))
                        end_dt = date_parser.parse(str(conv_updated))
                        calculated_duration = int((end_dt - start_dt).total_seconds())

                        if calculated_duration > 0:
                            call.duration = calculated_duration
                            call.started_at = start_dt.replace(tzinfo=None)
                            call.ended_at = end_dt.replace(tzinfo=None)
                            updated += 1
                            print(f"Call {call.id}: Updated duration to {calculated_duration}s")
                            continue

                    # Fallback: try message timestamps
                    conv_id = conv_data.get("id")
                    print(f"  Trying message timestamps, conv_id={conv_id}")
                    if conv_id:
                        msgs = await telnyx_ai.get_conversation_messages(conv_id)
                        print(f"  Got {len(msgs) if msgs else 0} messages")
                        if msgs and len(msgs) >= 2:
                            # Messages may be in reverse order, so use last element as start, first as end
                            # or just use min/max to be safe
                            first_ts = msgs[-1].get("created_at") or msgs[-1].get("timestamp")
                            last_ts = msgs[0].get("created_at") or msgs[0].get("timestamp")
                            print(f"  Oldest msg ts: {first_ts}, Newest msg ts: {last_ts}")

                            if first_ts and last_ts:
                                from dateutil import parser as date_parser
                                start_dt = date_parser.parse(str(first_ts))
                                end_dt = date_parser.parse(str(last_ts))
                                calculated_duration = int((end_dt - start_dt).total_seconds())
                                print(f"  Calculated duration: {calculated_duration}s")

                                if calculated_duration > 0:
                                    call.duration = calculated_duration
                                    call.started_at = start_dt.replace(tzinfo=None)
                                    call.ended_at = end_dt.replace(tzinfo=None)
                                    updated += 1
                                    print(f"Call {call.id}: Updated duration to {calculated_duration}s (from messages)")
                                    continue

                print(f"Call {call.id}: No conversation found or no timestamps")
                failed += 1

            except Exception as e:
                print(f"Call {call.id}: Error - {e}")
                failed += 1

        await db.commit()
        print(f"\nSummary: Updated {updated} calls, Failed {failed} calls")


if __name__ == "__main__":
    asyncio.run(backfill())
