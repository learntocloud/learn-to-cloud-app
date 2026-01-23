"""Tests for webhooks routes."""

from unittest.mock import MagicMock, patch

from httpx import AsyncClient


class TestClerkWebhook:
    """Tests for POST /api/webhooks/clerk endpoint."""

    @patch("routes.webhooks_routes.Webhook")
    @patch("routes.webhooks_routes.get_settings")
    async def test_successful_webhook_processing(
        self, mock_settings, mock_webhook_class, client: AsyncClient
    ):
        """Test successful webhook processing."""
        # Configure settings
        mock_settings.return_value.clerk_webhook_signing_secret = "test-secret"

        # Configure webhook verification (sync method, not async)
        mock_webhook = MagicMock()
        mock_webhook.verify.return_value = {
            "type": "user.created",
            "data": {
                "id": "user_webhook_test",
                "first_name": "Test",
                "email_addresses": [],
                "external_accounts": [],
            },
        }
        mock_webhook_class.return_value = mock_webhook

        response = await client.post(
            "/api/webhooks/clerk",
            content=b'{"type": "user.created", "data": {}}',
            headers={
                "svix-id": "svix_test_123",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,signature",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] in ("processed", "already_processed")

    async def test_returns_400_for_missing_headers(self, client: AsyncClient):
        """Test returns 400 when webhook headers are missing."""
        response = await client.post(
            "/api/webhooks/clerk",
            content=b'{"type": "user.created"}',
            # Missing svix headers
        )

        assert response.status_code == 400
        assert "Missing webhook headers" in response.json()["detail"]

    async def test_returns_400_for_partial_headers(self, client: AsyncClient):
        """Test returns 400 when some headers are missing."""
        response = await client.post(
            "/api/webhooks/clerk",
            content=b'{"type": "user.created"}',
            headers={
                "svix-id": "svix_test_123",
                # Missing svix-timestamp and svix-signature
            },
        )

        assert response.status_code == 400

    @patch("routes.webhooks_routes.get_settings")
    async def test_returns_500_when_secret_not_configured(
        self, mock_settings, client: AsyncClient
    ):
        """Test returns 500 when webhook secret not configured."""
        mock_settings.return_value.clerk_webhook_signing_secret = None

        response = await client.post(
            "/api/webhooks/clerk",
            content=b'{"type": "user.created"}',
            headers={
                "svix-id": "svix_test_123",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,signature",
            },
        )

        assert response.status_code == 500
        assert "not configured" in response.json()["detail"]

    @patch("routes.webhooks_routes.Webhook")
    @patch("routes.webhooks_routes.get_settings")
    async def test_returns_400_for_invalid_signature(
        self, mock_settings, mock_webhook_class, client: AsyncClient
    ):
        """Test returns 400 for invalid webhook signature."""
        from svix.webhooks import WebhookVerificationError

        mock_settings.return_value.clerk_webhook_signing_secret = "test-secret"

        mock_webhook = MagicMock()
        mock_webhook.verify.side_effect = WebhookVerificationError("Invalid signature")
        mock_webhook_class.return_value = mock_webhook

        response = await client.post(
            "/api/webhooks/clerk",
            content=b'{"type": "user.created"}',
            headers={
                "svix-id": "svix_test_123",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,invalid",
            },
        )

        assert response.status_code == 400
        assert "Invalid webhook signature" in response.json()["detail"]

    @patch("routes.webhooks_routes.Webhook")
    @patch("routes.webhooks_routes.get_settings")
    async def test_handles_user_created_event(
        self, mock_settings, mock_webhook_class, client: AsyncClient
    ):
        """Test handling user.created event."""
        mock_settings.return_value.clerk_webhook_signing_secret = "test-secret"

        mock_webhook = MagicMock()
        mock_webhook.verify.return_value = {
            "type": "user.created",
            "data": {
                "id": "user_created_event",
                "first_name": "New",
                "last_name": "User",
                "email_addresses": [
                    {"id": "email_1", "email_address": "new@example.com"}
                ],
                "primary_email_address_id": "email_1",
                "external_accounts": [],
            },
        }
        mock_webhook_class.return_value = mock_webhook

        response = await client.post(
            "/api/webhooks/clerk",
            content=b"{}",
            headers={
                "svix-id": "svix_user_created",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,signature",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "user.created"

    @patch("routes.webhooks_routes.Webhook")
    @patch("routes.webhooks_routes.get_settings")
    async def test_handles_user_updated_event(
        self, mock_settings, mock_webhook_class, client: AsyncClient
    ):
        """Test handling user.updated event."""
        mock_settings.return_value.clerk_webhook_signing_secret = "test-secret"

        mock_webhook = MagicMock()
        mock_webhook.verify.return_value = {
            "type": "user.updated",
            "data": {
                "id": "user_updated_event",
                "first_name": "Updated",
                "email_addresses": [],
                "external_accounts": [],
            },
        }
        mock_webhook_class.return_value = mock_webhook

        response = await client.post(
            "/api/webhooks/clerk",
            content=b"{}",
            headers={
                "svix-id": "svix_user_updated",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,signature",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "user.updated"

    @patch("routes.webhooks_routes.Webhook")
    @patch("routes.webhooks_routes.get_settings")
    async def test_handles_user_deleted_event(
        self, mock_settings, mock_webhook_class, client: AsyncClient
    ):
        """Test handling user.deleted event."""
        mock_settings.return_value.clerk_webhook_signing_secret = "test-secret"

        mock_webhook = MagicMock()
        mock_webhook.verify.return_value = {
            "type": "user.deleted",
            "data": {"id": "user_deleted_event"},
        }
        mock_webhook_class.return_value = mock_webhook

        response = await client.post(
            "/api/webhooks/clerk",
            content=b"{}",
            headers={
                "svix-id": "svix_user_deleted",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,signature",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "user.deleted"

    @patch("routes.webhooks_routes.Webhook")
    @patch("routes.webhooks_routes.get_settings")
    async def test_idempotency_returns_already_processed(
        self, mock_settings, mock_webhook_class, client: AsyncClient
    ):
        """Test that duplicate svix_id returns already_processed."""
        mock_settings.return_value.clerk_webhook_signing_secret = "test-secret"

        mock_webhook = MagicMock()
        mock_webhook.verify.return_value = {
            "type": "user.created",
            "data": {
                "id": "user_idempotent_test",
                "email_addresses": [],
                "external_accounts": [],
            },
        }
        mock_webhook_class.return_value = mock_webhook

        # First request
        response1 = await client.post(
            "/api/webhooks/clerk",
            content=b"{}",
            headers={
                "svix-id": "svix_idempotent_test",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,signature",
            },
        )

        # Second request with same svix-id
        response2 = await client.post(
            "/api/webhooks/clerk",
            content=b"{}",
            headers={
                "svix-id": "svix_idempotent_test",
                "svix-timestamp": "1234567890",
                "svix-signature": "v1,signature",
            },
        )

        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response2.json()["status"] == "already_processed"
