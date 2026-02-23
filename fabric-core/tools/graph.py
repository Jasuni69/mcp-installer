import html
import json
import os
from typing import Any, Dict, Optional, Tuple

import requests

from helpers.logging_config import get_logger
from helpers.utils.authentication import get_azure_credentials
from helpers.utils.context import mcp, __ctx_cache
from mcp.server.fastmcp import Context


logger = get_logger(__name__)


def _normalise_channel_message_content(
    content: str, content_type: str = "html"
) -> Tuple[str, str]:
    """Prepare Teams channel message content for Graph."""

    normalised_type = (content_type or "html").lower()
    if normalised_type not in {"html", "text", "markdown"}:
        raise ValueError(
            "Unsupported content_type. Must be one of 'html', 'text', or 'markdown'."
        )

    if normalised_type == "html":
        stripped = content.strip()
        if stripped.startswith("<") and stripped.endswith(">"):
            return normalised_type, stripped

        safe_html = html.escape(content)
        safe_html = safe_html.replace("\r\n", "\n").replace("\r", "\n")
        safe_html = safe_html.replace("\n", "<br>")
        return normalised_type, f"<div>{safe_html}</div>"

    return normalised_type, content


def _graph_headers(ctx: Context) -> Dict[str, str]:
    credential = get_azure_credentials(ctx.client_id, __ctx_cache)
    token = credential.get_token("https://graph.microsoft.com/.default")
    return {
        "Authorization": f"Bearer {token.token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _graph_request(
    ctx: Context,
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    headers = _graph_headers(ctx)
    response = requests.request(
        method=method.upper(),
        url=url,
        headers=headers,
        json=payload,
        timeout=120,
    )

    if response.status_code >= 400:
        logger.error(
            "Graph API error %s: %s", response.status_code, response.text[:500]
        )
        return {
            "status": response.status_code,
            "error": response.text,
        }

    if not response.text:
        return {"status": response.status_code}

    try:
        return response.json()
    except json.JSONDecodeError:
        return {"status": response.status_code, "raw": response.text}


@mcp.tool()
async def graph_user(email: str, ctx: Context) -> Dict[str, Any]:
    """Query Azure AD user profile details via Microsoft Graph."""

    try:
        if email.strip().lower() == "me":
            url = "https://graph.microsoft.com/v1.0/me"
        else:
            url = f"https://graph.microsoft.com/v1.0/users/{email}"
        return _graph_request(ctx, "get", url)
    except Exception as exc:
        logger.error("Error retrieving Graph user: %s", exc)
        return {"error": str(exc)}


def _parse_recipients(value: str) -> list:
    """Parse comma-separated email addresses into Graph recipient format."""
    return [
        {"emailAddress": {"address": addr.strip()}}
        for addr in value.split(",")
        if addr.strip()
    ]


@mcp.tool()
async def graph_mail(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    importance: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Send mail via Microsoft Graph on behalf of the current identity.

    Args:
        to: Recipient email address(es), comma-separated for multiple
        subject: Email subject line
        body: Email body (HTML supported)
        cc: CC recipient(s), comma-separated (optional)
        bcc: BCC recipient(s), comma-separated (optional)
        importance: Email importance: Low, Normal, or High (optional)
        ctx: FastMCP context
    """

    try:
        url = "https://graph.microsoft.com/v1.0/me/sendMail"
        message: Dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body,
            },
            "toRecipients": _parse_recipients(to),
        }
        if cc:
            message["ccRecipients"] = _parse_recipients(cc)
        if bcc:
            message["bccRecipients"] = _parse_recipients(bcc)
        if importance and importance in ("Low", "Normal", "High"):
            message["importance"] = importance

        payload = {
            "message": message,
            "saveToSentItems": True,
        }
        return _graph_request(ctx, "post", url, payload)
    except Exception as exc:
        logger.error("Error sending Graph mail: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def graph_teams_message(
    team_id: str,
    channel_id: str,
    text: str,
    content_type: str = "html",
    ctx: Context = None,
) -> Dict[str, Any]:
    """Post a message to a Teams channel via Microsoft Graph.

    Args:
        team_id: The target Microsoft Teams team identifier.
        channel_id: The channel identifier within the team.
        text: The message body to send.
        content_type: Graph contentType, defaults to "html". Can be "html", "text", "markdown".
        ctx: FastMCP context.
    """

    try:
        if ctx is None:
            raise ValueError("Context (ctx) must be provided.")

        normalised_type, message_body = _normalise_channel_message_content(text, content_type)

        url = f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages"
        payload = {
            "body": {
                "contentType": normalised_type,
                "content": message_body,
            }
        }
        return _graph_request(ctx, "post", url, payload)
    except Exception as exc:
        logger.error("Error posting Teams message: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def graph_drive(
    drive_id: str,
    path: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """List files in a OneDrive or SharePoint drive via Microsoft Graph."""

    try:
        if ctx is None:
            raise ValueError("Context (ctx) must be provided.")

        normalised_path = (path or "").strip("/")
        # Support "me" to browse the current user's OneDrive
        if drive_id.strip().lower() == "me":
            if normalised_path:
                url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{normalised_path}:/children"
            else:
                url = f"https://graph.microsoft.com/v1.0/me/drive/root/children"
        else:
            if normalised_path:
                url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{normalised_path}:/children"
            else:
                url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"

        return _graph_request(ctx, "get", url)
    except Exception as exc:
        logger.error("Error listing drive items: %s", exc)
        return {"error": str(exc)}




@mcp.tool()
async def list_teams(
    ctx: Context = None,
) -> Dict[str, Any]:
    """List all Microsoft Teams the current user is a member of.

    Returns team IDs and display names needed for posting messages.
    """
    try:
        if ctx is None:
            raise ValueError("Context (ctx) must be provided.")
        url = "https://graph.microsoft.com/v1.0/me/joinedTeams"
        return _graph_request(ctx, "get", url)
    except Exception as exc:
        logger.error("Error listing teams: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def list_channels(
    team_id: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """List all channels in a Microsoft Teams team.

    Args:
        team_id: The team ID (get from list_teams)
        ctx: FastMCP context
    Returns:
        List of channels with IDs and display names.
    """
    try:
        if ctx is None:
            raise ValueError("Context (ctx) must be provided.")
        url = f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels"
        return _graph_request(ctx, "get", url)
    except Exception as exc:
        logger.error("Error listing channels: %s", exc)
        return {"error": str(exc)}


# Alias management for Teams channels
def _aliases_file_path() -> str:
    # Store aliases at the repository root for persistence
    root_dir = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(root_dir, "teams_channel_aliases.json")


def _load_aliases() -> Dict[str, Dict[str, str]]:
    path = _aliases_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception:
        # If file is corrupt/unreadable, start fresh rather than failing tool calls
        return {}


def _save_aliases(aliases: Dict[str, Dict[str, str]]) -> None:
    path = _aliases_file_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(aliases, f, indent=2, ensure_ascii=False)


@mcp.tool()
async def save_teams_channel_alias(
    alias: str,
    team_id: str,
    channel_id: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Create or update a named alias for a Teams channel (team_id + channel_id)."""

    try:
        if ctx is None:
            raise ValueError("Context (ctx) must be provided.")

        normalised = (alias or "").strip().lower()
        if not normalised:
            raise ValueError("Alias must be a non-empty string.")

        aliases = _load_aliases()
        aliases[normalised] = {"team_id": team_id, "channel_id": channel_id}
        _save_aliases(aliases)
        return {"alias": normalised, "team_id": team_id, "channel_id": channel_id}
    except Exception as exc:
        logger.error("Error saving Teams channel alias: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def list_teams_channel_aliases(ctx: Context = None) -> Dict[str, Any]:
    """List all saved Teams channel aliases."""

    try:
        if ctx is None:
            raise ValueError("Context (ctx) must be provided.")
        return {"aliases": _load_aliases()}
    except Exception as exc:
        logger.error("Error listing Teams channel aliases: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def delete_teams_channel_alias(alias: str, ctx: Context = None) -> Dict[str, Any]:
    """Delete a saved Teams channel alias."""

    try:
        if ctx is None:
            raise ValueError("Context (ctx) must be provided.")
        normalised = (alias or "").strip().lower()
        aliases = _load_aliases()
        if normalised in aliases:
            removed = aliases.pop(normalised)
            _save_aliases(aliases)
            return {"deleted": normalised, "value": removed}
        return {"deleted": None}
    except Exception as exc:
        logger.error("Error deleting Teams channel alias: %s", exc)
        return {"error": str(exc)}


@mcp.tool()
async def graph_teams_message_alias(
    alias: str,
    text: str,
    content_type: str = "html",
    ctx: Context = None,
) -> Dict[str, Any]:
    """Post a message to a Teams channel using a saved alias.

    Resolves the alias into `(team_id, channel_id)` and forwards to `graph_teams_message`.
    """

    try:
        if ctx is None:
            raise ValueError("Context (ctx) must be provided.")
        normalised = (alias or "").strip().lower()
        aliases = _load_aliases()
        if normalised not in aliases:
            raise ValueError(f"Alias not found: {normalised}")
        mapping = aliases[normalised]
        return await graph_teams_message(
            mapping["team_id"],
            mapping["channel_id"],
            text,
            content_type,
            ctx,
        )
    except Exception as exc:
        logger.error("Error posting Teams message via alias: %s", exc)
        return {"error": str(exc)}

