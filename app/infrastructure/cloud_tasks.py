"""Cloud Tasks client wrapper for async message processing."""

import json
from typing import Any

from google.cloud import tasks_v2
from google.protobuf import duration_pb2

from app.settings import settings


class CloudTasksClient:
    """Cloud Tasks client wrapper for queuing async jobs."""

    def __init__(self) -> None:
        """Initialize Cloud Tasks client."""
        self.client = tasks_v2.CloudTasksClient()
        self.project = settings.gcp_project_id
        self.location = settings.cloud_tasks_location
        self.queue_name = settings.cloud_tasks_queue_name
        self.queue_path = self.client.queue_path(
            self.project,
            self.location,
            self.queue_name,
        )

    def create_task(
        self,
        payload: dict[str, Any],
        url: str,
        delay_seconds: int = 0,
    ) -> str:
        """Create a Cloud Task.
        
        Args:
            payload: Task payload (will be JSON serialized)
            url: Target URL for the task
            delay_seconds: Delay before executing the task
            
        Returns:
            Task name/path
        """
        # Create the task
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(payload).encode(),
            }
        }
        
        # Add delay if specified
        if delay_seconds > 0:
            from datetime import datetime, timedelta, timezone
            from google.protobuf import timestamp_pb2
            schedule_time = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            timestamp = timestamp_pb2.Timestamp()
            timestamp.FromDatetime(schedule_time)
            task["schedule_time"] = timestamp
        
        # Create the task
        response = self.client.create_task(
            request={
                "parent": self.queue_path,
                "task": task,
            }
        )
        
        return response.name

    async def create_task_async(
        self,
        payload: dict[str, Any],
        url: str,
        delay_seconds: int = 0,
    ) -> str:
        """Create a Cloud Task asynchronously.
        
        Args:
            payload: Task payload (will be JSON serialized)
            url: Target URL for the task
            delay_seconds: Delay before executing the task
            
        Returns:
            Task name/path
        """
        # For async operations, we'll use the sync client in an executor
        # In production, you might want to use async Cloud Tasks client
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.create_task,
            payload,
            url,
            delay_seconds,
        )

