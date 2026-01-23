"""Encrypt sensitive credential fields in tenant config tables.

This migration:
1. Expands column sizes to accommodate encrypted values (encrypted values are ~2x larger)
2. Optionally encrypts existing plaintext values if FIELD_ENCRYPTION_KEY is set

Affected tables and columns:
- tenant_sms_configs: twilio_auth_token, telnyx_api_key
- tenant_email_configs: gmail_refresh_token, gmail_access_token, sendgrid_webhook_secret, sendgrid_api_key
- tenant_customer_service_configs: zapier_callback_secret

IMPORTANT: After running this migration, set FIELD_ENCRYPTION_KEY in production and
re-run the encrypt_existing_credentials() function to encrypt any remaining plaintext values.

Revision ID: encrypt_sensitive_credentials
Revises: remove_voxie_provider_fields
Create Date: 2026-01-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


revision = 'encrypt_sensitive_credentials'
down_revision = 'remove_voxie_provider_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Expand column sizes to accommodate encrypted values
    # Encrypted values are roughly 2x the size of plaintext due to base64 + Fernet overhead

    # tenant_sms_configs
    op.alter_column(
        'tenant_sms_configs',
        'twilio_auth_token',
        type_=sa.Text(),
        existing_type=sa.String(255),
        existing_nullable=True
    )
    op.alter_column(
        'tenant_sms_configs',
        'telnyx_api_key',
        type_=sa.Text(),
        existing_type=sa.String(255),
        existing_nullable=True
    )

    # tenant_email_configs - these are already Text, but let's ensure consistency
    # gmail_refresh_token and gmail_access_token are already Text

    op.alter_column(
        'tenant_email_configs',
        'sendgrid_webhook_secret',
        type_=sa.Text(),
        existing_type=sa.String(255),
        existing_nullable=True
    )
    op.alter_column(
        'tenant_email_configs',
        'sendgrid_api_key',
        type_=sa.Text(),
        existing_type=sa.String(255),
        existing_nullable=True
    )

    # tenant_customer_service_configs
    op.alter_column(
        'tenant_customer_service_configs',
        'zapier_callback_secret',
        type_=sa.Text(),
        existing_type=sa.String(255),
        existing_nullable=True
    )

    # Encrypt existing data if encryption key is available
    encrypt_existing_credentials()


def encrypt_existing_credentials() -> None:
    """Encrypt any existing plaintext credentials in the database.

    This function is safe to run multiple times - it only encrypts
    values that don't already have the 'enc:' prefix.
    """
    try:
        from app.core.encryption import get_encryption_service, encrypt_field
    except ImportError:
        print("Encryption module not available - skipping encryption of existing data")
        return

    encryption_service = get_encryption_service()
    if not encryption_service.is_enabled:
        print("FIELD_ENCRYPTION_KEY not set - existing credentials will remain unencrypted")
        print("Set FIELD_ENCRYPTION_KEY and run this migration again to encrypt existing data")
        return

    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        # Encrypt tenant_sms_configs credentials
        result = session.execute(sa.text("""
            SELECT id, twilio_auth_token, telnyx_api_key
            FROM tenant_sms_configs
            WHERE (twilio_auth_token IS NOT NULL AND twilio_auth_token NOT LIKE 'enc:%')
               OR (telnyx_api_key IS NOT NULL AND telnyx_api_key NOT LIKE 'enc:%')
        """))
        for row in result:
            updates = {}
            if row.twilio_auth_token and not row.twilio_auth_token.startswith('enc:'):
                updates['twilio_auth_token'] = encrypt_field(row.twilio_auth_token)
            if row.telnyx_api_key and not row.telnyx_api_key.startswith('enc:'):
                updates['telnyx_api_key'] = encrypt_field(row.telnyx_api_key)
            if updates:
                session.execute(
                    sa.text("UPDATE tenant_sms_configs SET twilio_auth_token = :token, telnyx_api_key = :key WHERE id = :id"),
                    {"token": updates.get('twilio_auth_token', row.twilio_auth_token),
                     "key": updates.get('telnyx_api_key', row.telnyx_api_key),
                     "id": row.id}
                )
        print(f"Encrypted credentials in tenant_sms_configs")

        # Encrypt tenant_email_configs credentials
        result = session.execute(sa.text("""
            SELECT id, gmail_refresh_token, gmail_access_token, sendgrid_webhook_secret, sendgrid_api_key
            FROM tenant_email_configs
            WHERE (gmail_refresh_token IS NOT NULL AND gmail_refresh_token NOT LIKE 'enc:%')
               OR (gmail_access_token IS NOT NULL AND gmail_access_token NOT LIKE 'enc:%')
               OR (sendgrid_webhook_secret IS NOT NULL AND sendgrid_webhook_secret NOT LIKE 'enc:%')
               OR (sendgrid_api_key IS NOT NULL AND sendgrid_api_key NOT LIKE 'enc:%')
        """))
        for row in result:
            updates = {
                'gmail_refresh_token': encrypt_field(row.gmail_refresh_token) if row.gmail_refresh_token and not row.gmail_refresh_token.startswith('enc:') else row.gmail_refresh_token,
                'gmail_access_token': encrypt_field(row.gmail_access_token) if row.gmail_access_token and not row.gmail_access_token.startswith('enc:') else row.gmail_access_token,
                'sendgrid_webhook_secret': encrypt_field(row.sendgrid_webhook_secret) if row.sendgrid_webhook_secret and not row.sendgrid_webhook_secret.startswith('enc:') else row.sendgrid_webhook_secret,
                'sendgrid_api_key': encrypt_field(row.sendgrid_api_key) if row.sendgrid_api_key and not row.sendgrid_api_key.startswith('enc:') else row.sendgrid_api_key,
            }
            session.execute(
                sa.text("""UPDATE tenant_email_configs
                          SET gmail_refresh_token = :refresh, gmail_access_token = :access,
                              sendgrid_webhook_secret = :secret, sendgrid_api_key = :key
                          WHERE id = :id"""),
                {"refresh": updates['gmail_refresh_token'],
                 "access": updates['gmail_access_token'],
                 "secret": updates['sendgrid_webhook_secret'],
                 "key": updates['sendgrid_api_key'],
                 "id": row.id}
            )
        print(f"Encrypted credentials in tenant_email_configs")

        # Encrypt tenant_customer_service_configs credentials
        result = session.execute(sa.text("""
            SELECT id, zapier_callback_secret
            FROM tenant_customer_service_configs
            WHERE zapier_callback_secret IS NOT NULL AND zapier_callback_secret NOT LIKE 'enc:%'
        """))
        for row in result:
            encrypted = encrypt_field(row.zapier_callback_secret)
            session.execute(
                sa.text("UPDATE tenant_customer_service_configs SET zapier_callback_secret = :secret WHERE id = :id"),
                {"secret": encrypted, "id": row.id}
            )
        print(f"Encrypted credentials in tenant_customer_service_configs")

        session.commit()
        print("Successfully encrypted all existing credentials")

    except Exception as e:
        session.rollback()
        print(f"Error encrypting credentials: {e}")
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Revert column types back to String.

    NOTE: This does NOT decrypt the data - encrypted values will remain encrypted.
    To fully revert, you would need to decrypt values first using the encryption key.
    """
    # Revert column types (encrypted data will remain encrypted but may be truncated)
    op.alter_column(
        'tenant_customer_service_configs',
        'zapier_callback_secret',
        type_=sa.String(255),
        existing_type=sa.Text(),
        existing_nullable=True
    )

    op.alter_column(
        'tenant_email_configs',
        'sendgrid_api_key',
        type_=sa.String(255),
        existing_type=sa.Text(),
        existing_nullable=True
    )
    op.alter_column(
        'tenant_email_configs',
        'sendgrid_webhook_secret',
        type_=sa.String(255),
        existing_type=sa.Text(),
        existing_nullable=True
    )

    op.alter_column(
        'tenant_sms_configs',
        'telnyx_api_key',
        type_=sa.String(255),
        existing_type=sa.Text(),
        existing_nullable=True
    )
    op.alter_column(
        'tenant_sms_configs',
        'twilio_auth_token',
        type_=sa.String(255),
        existing_type=sa.Text(),
        existing_nullable=True
    )
