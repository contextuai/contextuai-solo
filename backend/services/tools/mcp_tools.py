"""
MCP (Model Context Protocol) Server tools for Strands Agent.
Connects to external MCP servers to dynamically discover and invoke their tools.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from strands.tools import tool

logger = logging.getLogger(__name__)


class MCPTools:
    """
    MCP Server tool class for connecting to external MCP-compliant servers.

    Uses the Strands SDK's native MCP support to:
    - Connect to MCP servers via SSE or Streamable HTTP transport
    - Discover available tools from the server
    - Proxy tool invocations through the MCP protocol
    """

    def __init__(self, persona_id: str, credentials: Dict[str, Any]):
        """
        Initialize MCP tools with connection credentials.

        Args:
            persona_id: Unique persona identifier
            credentials: MCP server connection details:
                - endpoint_url: Server endpoint URL
                - transport: "sse" or "streamable-http"
                - headers: Optional custom headers (JSON dict)
        """
        self.persona_id = persona_id
        self.credentials = credentials
        self.endpoint_url = credentials.get("endpoint_url", "")
        self.transport = credentials.get("transport", "sse")
        self.custom_headers = credentials.get("headers", {})
        self._mcp_client = None

        logger.info(
            f"MCPTools initialized for persona {persona_id}, "
            f"endpoint: {self.endpoint_url}, transport: {self.transport}"
        )

    def get_tools(self):
        """Return MCP management tools as a list for Strands Agent."""
        return [
            self.discover_tools,
            self.call_mcp_tool,
            self.list_resources,
        ]

    def get_mcp_server_config(self) -> Dict[str, Any]:
        """
        Return an MCP server configuration dict suitable for Strands Agent.

        This can be passed to Agent(tools=[...]) alongside the MCPClient from strands.

        Returns:
            Dict with endpoint_url, transport, and headers for MCP client setup
        """
        return {
            "endpoint_url": self.endpoint_url,
            "transport": self.transport,
            "headers": self.custom_headers,
        }

    @tool
    async def discover_tools(self) -> Dict[str, Any]:
        """
        Discover available tools from the connected MCP server.

        Performs the MCP initialize handshake and calls tools/list to enumerate
        all tools exposed by the server.

        Returns:
            Dictionary with discovered tools:
            {
                "success": bool,
                "tools": List of { name, description, input_schema },
                "tool_count": int,
                "server_info": { name, version },
                "error": Optional[str]
            }
        """
        try:
            import httpx

            start_time = time.time()

            async with httpx.AsyncClient(timeout=15) as client:
                headers = {"Content-Type": "application/json"}
                if self.custom_headers:
                    if isinstance(self.custom_headers, str):
                        import json
                        headers.update(json.loads(self.custom_headers))
                    elif isinstance(self.custom_headers, dict):
                        headers.update(self.custom_headers)

                # MCP JSON-RPC initialize
                init_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "contextuai", "version": "1.0.0"},
                    },
                }

                resp = await client.post(
                    self.endpoint_url,
                    json=init_payload,
                    headers=headers,
                )
                resp.raise_for_status()
                init_result = resp.json().get("result", {})

                server_info = init_result.get("serverInfo", {})

                # Send initialized notification
                await client.post(
                    self.endpoint_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                    },
                    headers=headers,
                )

                # List tools
                tools_payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                }

                tools_resp = await client.post(
                    self.endpoint_url,
                    json=tools_payload,
                    headers=headers,
                )
                tools_resp.raise_for_status()
                tools_result = tools_resp.json().get("result", {})
                tools_list = tools_result.get("tools", [])

            response_time = round((time.time() - start_time) * 1000)

            discovered = [
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "input_schema": t.get("inputSchema", {}),
                }
                for t in tools_list
            ]

            return {
                "success": True,
                "tools": discovered,
                "tool_count": len(discovered),
                "server_info": server_info,
                "response_time_ms": response_time,
            }

        except Exception as e:
            logger.error(f"Error discovering MCP tools: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to discover tools: {str(e)}",
                "tools": [],
                "tool_count": 0,
            }

    @tool
    async def call_mcp_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call a specific tool on the MCP server.

        Args:
            tool_name: Name of the MCP tool to invoke
            arguments: Tool arguments as a dictionary (must match the tool's input schema)

        Returns:
            Dictionary with tool result:
            {
                "success": bool,
                "tool_name": str,
                "result": Any (tool output content),
                "error": Optional[str]
            }
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                headers = {"Content-Type": "application/json"}
                if self.custom_headers:
                    if isinstance(self.custom_headers, str):
                        import json
                        headers.update(json.loads(self.custom_headers))
                    elif isinstance(self.custom_headers, dict):
                        headers.update(self.custom_headers)

                payload = {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments or {},
                    },
                }

                resp = await client.post(
                    self.endpoint_url,
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                response_data = resp.json()

                if "error" in response_data:
                    return {
                        "success": False,
                        "tool_name": tool_name,
                        "error": response_data["error"].get("message", str(response_data["error"])),
                    }

                result = response_data.get("result", {})
                content = result.get("content", [])

                # Extract text content from MCP response
                text_parts = []
                for item in content:
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))

                return {
                    "success": True,
                    "tool_name": tool_name,
                    "result": "\n".join(text_parts) if text_parts else content,
                    "is_error": result.get("isError", False),
                }

        except Exception as e:
            logger.error(f"Error calling MCP tool '{tool_name}': {e}", exc_info=True)
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"Failed to call tool: {str(e)}",
            }

    @tool
    async def list_resources(self) -> Dict[str, Any]:
        """
        List resources available from the MCP server.

        MCP resources are data sources the server exposes (files, database entries, etc.)
        that can be read by the client.

        Returns:
            Dictionary with resource list:
            {
                "success": bool,
                "resources": List of { uri, name, description, mimeType },
                "count": int,
                "error": Optional[str]
            }
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15) as client:
                headers = {"Content-Type": "application/json"}
                if self.custom_headers:
                    if isinstance(self.custom_headers, str):
                        import json
                        headers.update(json.loads(self.custom_headers))
                    elif isinstance(self.custom_headers, dict):
                        headers.update(self.custom_headers)

                payload = {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "resources/list",
                    "params": {},
                }

                resp = await client.post(
                    self.endpoint_url,
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                result = resp.json().get("result", {})
                resources = result.get("resources", [])

            formatted = [
                {
                    "uri": r.get("uri", ""),
                    "name": r.get("name", ""),
                    "description": r.get("description", ""),
                    "mimeType": r.get("mimeType", ""),
                }
                for r in resources
            ]

            return {
                "success": True,
                "resources": formatted,
                "count": len(formatted),
            }

        except Exception as e:
            logger.error(f"Error listing MCP resources: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to list resources: {str(e)}",
                "resources": [],
                "count": 0,
            }
