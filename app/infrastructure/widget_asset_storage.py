"""Widget asset storage service using Google Cloud Storage."""

import logging
import uuid
from typing import BinaryIO

from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError

from app.settings import settings

logger = logging.getLogger(__name__)

# Constants for upload validation
MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024  # 1 MB
ALLOWED_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/svg+xml": "svg",
}
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}


class WidgetAssetStorageError(Exception):
    """Custom exception for widget asset storage errors."""
    pass


class WidgetAssetStorage:
    """Service for storing and managing widget assets in GCS."""

    def __init__(self):
        """Initialize the storage client."""
        self._client: storage.Client | None = None
        self._bucket: storage.Bucket | None = None

    @property
    def client(self) -> storage.Client:
        """Lazy-load the GCS client."""
        if self._client is None:
            self._client = storage.Client(project=settings.gcp_project_id)
        return self._client

    @property
    def bucket(self) -> storage.Bucket:
        """Get the configured bucket."""
        if self._bucket is None:
            bucket_name = settings.gcs_widget_assets_bucket
            if not bucket_name:
                raise WidgetAssetStorageError(
                    "GCS_WIDGET_ASSETS_BUCKET is not configured"
                )
            self._bucket = self.client.bucket(bucket_name)
        return self._bucket

    def _get_blob_path(self, tenant_id: int, asset_id: str, extension: str) -> str:
        """Generate the blob path for a tenant asset.

        Path format: tenants/{tenant_id}/widget-assets/{asset_id}.{ext}
        """
        return f"tenants/{tenant_id}/widget-assets/{asset_id}.{extension}"

    def _get_public_url(self, blob_name: str) -> str:
        """Generate the public URL for a blob.

        Uses the standard GCS public URL format.
        """
        bucket_name = settings.gcs_widget_assets_bucket
        return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"

    def validate_file(
        self,
        content_type: str | None,
        file_size: int,
        filename: str | None = None
    ) -> tuple[bool, str | None, str | None]:
        """Validate file type and size.

        Args:
            content_type: MIME type of the file
            file_size: Size of the file in bytes
            filename: Original filename (for extension fallback)

        Returns:
            Tuple of (is_valid, error_message, extension)
        """
        # Check file size
        if file_size > MAX_FILE_SIZE_BYTES:
            return (
                False,
                f"File size {file_size} bytes exceeds maximum of {MAX_FILE_SIZE_BYTES} bytes (1 MB)",
                None
            )

        if file_size == 0:
            return False, "File is empty", None

        # Check content type
        extension = None
        if content_type and content_type in ALLOWED_CONTENT_TYPES:
            extension = ALLOWED_CONTENT_TYPES[content_type]
        elif filename:
            # Fallback to filename extension
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else None
            if ext in ALLOWED_EXTENSIONS:
                extension = ext

        if not extension:
            allowed = ", ".join(ALLOWED_CONTENT_TYPES.keys())
            return (
                False,
                f"Invalid file type. Allowed types: {allowed}",
                None
            )

        return True, None, extension

    async def upload_asset(
        self,
        tenant_id: int,
        file_data: BinaryIO | bytes,
        content_type: str,
        filename: str | None = None,
    ) -> dict:
        """Upload a widget asset to GCS.

        Args:
            tenant_id: The tenant ID for isolation
            file_data: File data (binary file object or bytes)
            content_type: MIME type of the file
            filename: Original filename

        Returns:
            Dict with asset_id, public_url, content_type, size_bytes

        Raises:
            WidgetAssetStorageError: If upload fails
        """
        # Read file data if it's a file object
        if hasattr(file_data, "read"):
            data = file_data.read()
        else:
            data = file_data

        file_size = len(data)

        # Validate
        is_valid, error, extension = self.validate_file(
            content_type, file_size, filename
        )
        if not is_valid:
            raise WidgetAssetStorageError(error)

        # Generate unique asset ID
        asset_id = str(uuid.uuid4())
        blob_path = self._get_blob_path(tenant_id, asset_id, extension)

        try:
            blob = self.bucket.blob(blob_path)

            # Set cache control for better performance
            blob.cache_control = "public, max-age=31536000"  # 1 year

            # Upload with content type
            blob.upload_from_string(
                data,
                content_type=content_type,
            )

            # Make the blob publicly readable
            blob.make_public()

            public_url = self._get_public_url(blob_path)

            logger.info(
                f"Uploaded widget asset for tenant {tenant_id}: "
                f"asset_id={asset_id}, size={file_size}, type={content_type}"
            )

            return {
                "asset_id": asset_id,
                "public_url": public_url,
                "content_type": content_type,
                "size_bytes": file_size,
            }

        except GoogleCloudError as e:
            logger.error(f"GCS upload failed for tenant {tenant_id}: {e}")
            raise WidgetAssetStorageError(f"Failed to upload asset: {e}")

    async def delete_asset(self, tenant_id: int, asset_id: str, extension: str) -> bool:
        """Delete a widget asset from GCS.

        Args:
            tenant_id: The tenant ID
            asset_id: The asset ID to delete
            extension: File extension

        Returns:
            True if deleted, False if not found
        """
        blob_path = self._get_blob_path(tenant_id, asset_id, extension)

        try:
            blob = self.bucket.blob(blob_path)
            if blob.exists():
                blob.delete()
                logger.info(f"Deleted widget asset: tenant={tenant_id}, asset={asset_id}")
                return True
            return False
        except GoogleCloudError as e:
            logger.error(f"GCS delete failed: {e}")
            raise WidgetAssetStorageError(f"Failed to delete asset: {e}")


# Global instance
widget_asset_storage = WidgetAssetStorage()
