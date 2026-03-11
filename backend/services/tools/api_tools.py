"""
API/HTTP request tools for Strands Agent.
Provides HTTP request capabilities with various authentication methods.
"""

import os
import logging
import json
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse, urlencode
from strands.tools import tool
import asyncio
import aiohttp
import base64
from datetime import datetime

logger = logging.getLogger(__name__)


class APITools:
    """API/HTTP request tools for personas with API integration capabilities."""

    def __init__(self):
        """Initialize API tools with security configurations."""
        self.environment = os.getenv("ENVIRONMENT", "dev")

        # Request limits
        self.timeout = 30  # seconds
        self.max_response_size = 10 * 1024 * 1024  # 10 MB
        self.max_redirects = 5

        # User agent
        self.user_agent = "ContextuAI-API-Agent/1.0"

        # Default headers
        self.default_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate"
        }

        # Blocked hosts for security (in production)
        self.blocked_hosts = []
        if self.environment == "prod":
            self.blocked_hosts = [
                "localhost",
                "127.0.0.1",
                "0.0.0.0",
                "169.254.169.254"  # AWS metadata endpoint
            ]

        logger.info(f"APITools initialized for environment: {self.environment}")

    def get_tools(self):
        """Return all API operation tools."""
        return [
            self.http_request,
            self.graphql_request,
            self.rest_api_call,
            self.webhook_send,
            self.api_health_check
        ]

    def _is_safe_url(self, url: str) -> bool:
        """Check if URL is safe to access."""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname

            if not hostname:
                return False

            # Check against blocked hosts
            if hostname in self.blocked_hosts:
                logger.warning(f"Blocked access to host: {hostname}")
                return False

            # Block private IP ranges in production
            if self.environment == "prod":
                # Simple check for common private IPs
                if hostname.startswith("192.168.") or hostname.startswith("10.") or hostname.startswith("172."):
                    logger.warning(f"Blocked access to private IP: {hostname}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error checking URL safety: {e}")
            return False

    @tool
    async def http_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        auth_type: Optional[str] = None,
        auth_credentials: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with various options.

        Args:
            url: Target URL
            method: HTTP method (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS)
            headers: Additional headers to send
            params: URL parameters
            data: Form data to send
            json_data: JSON data to send
            auth_type: Authentication type (basic, bearer, api_key)
            auth_credentials: Authentication credentials
            follow_redirects: Whether to follow redirects

        Returns:
            Dictionary with response data
        """
        try:
            # Validate URL
            if not self._is_safe_url(url):
                return {
                    "success": False,
                    "error": "URL is not allowed",
                    "url": url
                }

            # Validate method
            method = method.upper()
            if method not in ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]:
                return {
                    "success": False,
                    "error": f"Invalid HTTP method: {method}"
                }

            # Prepare headers
            request_headers = self.default_headers.copy()
            if headers:
                request_headers.update(headers)

            # Handle authentication
            if auth_type and auth_credentials:
                auth_header = self._build_auth_header(auth_type, auth_credentials)
                if auth_header:
                    request_headers.update(auth_header)
                else:
                    return {
                        "success": False,
                        "error": f"Invalid authentication type or credentials"
                    }

            # Build URL with params
            if params:
                url = f"{url}?{urlencode(params)}"

            # Prepare request data
            request_kwargs = {
                "headers": request_headers,
                "timeout": self.timeout,
                "allow_redirects": follow_redirects,
                "max_redirects": self.max_redirects
            }

            if json_data:
                request_kwargs["json"] = json_data
            elif data:
                request_kwargs["data"] = data

            # Make request
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, **request_kwargs) as response:
                    # Check response size
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > self.max_response_size:
                        return {
                            "success": False,
                            "error": f"Response too large: {content_length} bytes",
                            "url": url
                        }

                    # Get response content
                    content_type = response.headers.get("Content-Type", "")

                    if "application/json" in content_type:
                        try:
                            response_data = await response.json()
                        except json.JSONDecodeError:
                            response_data = await response.text()
                    else:
                        response_data = await response.text()
                        # Limit text response size
                        if len(response_data) > self.max_response_size:
                            response_data = response_data[:self.max_response_size]
                            truncated = True
                        else:
                            truncated = False

                    result = {
                        "success": response.status < 400,
                        "url": str(response.url),
                        "method": method,
                        "status_code": response.status,
                        "status_text": response.reason,
                        "headers": dict(response.headers),
                        "content_type": content_type,
                        "data": response_data
                    }

                    if "truncated" in locals():
                        result["truncated"] = truncated

                    logger.info(f"HTTP {method} request to {url}: status {response.status}")
                    return result

        except asyncio.TimeoutError:
            logger.error(f"Timeout on {method} request to {url}")
            return {
                "success": False,
                "error": f"Request timeout after {self.timeout} seconds",
                "url": url,
                "method": method
            }
        except Exception as e:
            logger.error(f"Error in HTTP request to {url}: {e}")
            return {
                "success": False,
                "error": f"Request failed: {str(e)}",
                "url": url,
                "method": method
            }

    def _build_auth_header(self, auth_type: str, credentials: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Build authentication header based on type."""
        try:
            auth_type = auth_type.lower()

            if auth_type == "basic":
                username = credentials.get("username", "")
                password = credentials.get("password", "")
                if username and password:
                    auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
                    return {"Authorization": f"Basic {auth_string}"}

            elif auth_type == "bearer":
                token = credentials.get("token", "")
                if token:
                    return {"Authorization": f"Bearer {token}"}

            elif auth_type == "api_key":
                key_name = credentials.get("key_name", "X-API-Key")
                key_value = credentials.get("key_value", "")
                if key_value:
                    return {key_name: key_value}

            return None

        except Exception as e:
            logger.error(f"Error building auth header: {e}")
            return None

    @tool
    async def graphql_request(
        self,
        url: str,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_type: Optional[str] = None,
        auth_credentials: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Make a GraphQL request.

        Args:
            url: GraphQL endpoint URL
            query: GraphQL query string
            variables: Query variables
            headers: Additional headers
            auth_type: Authentication type
            auth_credentials: Authentication credentials

        Returns:
            Dictionary with GraphQL response
        """
        try:
            # Prepare GraphQL payload
            payload = {"query": query}
            if variables:
                payload["variables"] = variables

            # Make POST request to GraphQL endpoint
            result = await self.http_request(
                url=url,
                method="POST",
                json_data=payload,
                headers=headers,
                auth_type=auth_type,
                auth_credentials=auth_credentials
            )

            if result["success"] and isinstance(result.get("data"), dict):
                # Extract GraphQL response
                graphql_response = result["data"]

                if "errors" in graphql_response:
                    return {
                        "success": False,
                        "errors": graphql_response["errors"],
                        "data": graphql_response.get("data"),
                        "url": url
                    }
                else:
                    return {
                        "success": True,
                        "data": graphql_response.get("data"),
                        "url": url
                    }
            else:
                return result

        except Exception as e:
            logger.error(f"GraphQL request failed: {e}")
            return {
                "success": False,
                "error": f"GraphQL request failed: {str(e)}",
                "url": url
            }

    @tool
    async def rest_api_call(
        self,
        base_url: str,
        endpoint: str,
        method: str = "GET",
        path_params: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        body: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        api_key: Optional[str] = None,
        api_key_header: str = "X-API-Key"
    ) -> Dict[str, Any]:
        """
        Make a RESTful API call with convenient parameter handling.

        Args:
            base_url: Base URL of the API
            endpoint: API endpoint path
            method: HTTP method
            path_params: Path parameters to substitute in endpoint
            query_params: Query parameters
            body: Request body
            headers: Additional headers
            api_key: API key for authentication
            api_key_header: Header name for API key

        Returns:
            Dictionary with API response
        """
        try:
            # Build full URL
            full_endpoint = endpoint
            if path_params:
                for key, value in path_params.items():
                    full_endpoint = full_endpoint.replace(f"{{{key}}}", str(value))

            url = f"{base_url.rstrip('/')}/{full_endpoint.lstrip('/')}"

            # Prepare auth if API key provided
            auth_type = None
            auth_credentials = None
            if api_key:
                auth_type = "api_key"
                auth_credentials = {
                    "key_name": api_key_header,
                    "key_value": api_key
                }

            # Make request
            result = await self.http_request(
                url=url,
                method=method,
                params=query_params,
                json_data=body if isinstance(body, dict) else None,
                data=body if not isinstance(body, dict) else None,
                headers=headers,
                auth_type=auth_type,
                auth_credentials=auth_credentials
            )

            # Add endpoint info to result
            result["endpoint"] = endpoint
            result["base_url"] = base_url

            logger.info(f"REST API call to {endpoint}: status {result.get('status_code')}")
            return result

        except Exception as e:
            logger.error(f"REST API call failed: {e}")
            return {
                "success": False,
                "error": f"REST API call failed: {str(e)}",
                "base_url": base_url,
                "endpoint": endpoint
            }

    @tool
    async def webhook_send(
        self,
        webhook_url: str,
        payload: Dict[str, Any],
        event_type: Optional[str] = None,
        secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send data to a webhook endpoint.

        Args:
            webhook_url: Webhook URL
            payload: Data to send
            event_type: Optional event type header
            secret: Optional webhook secret for signing

        Returns:
            Dictionary with webhook response
        """
        try:
            # Prepare headers
            headers = {
                "Content-Type": "application/json"
            }

            if event_type:
                headers["X-Event-Type"] = event_type

            # Add timestamp
            timestamp = datetime.utcnow().isoformat() + "Z"
            headers["X-Timestamp"] = timestamp

            # Sign payload if secret provided
            if secret:
                import hmac
                import hashlib

                # Create signature
                message = f"{timestamp}.{json.dumps(payload, sort_keys=True)}"
                signature = hmac.new(
                    secret.encode(),
                    message.encode(),
                    hashlib.sha256
                ).hexdigest()
                headers["X-Signature"] = signature

            # Send webhook
            result = await self.http_request(
                url=webhook_url,
                method="POST",
                json_data=payload,
                headers=headers,
                follow_redirects=False  # Don't follow redirects for webhooks
            )

            # Add webhook-specific info
            result["event_type"] = event_type
            result["timestamp"] = timestamp

            logger.info(f"Webhook sent to {webhook_url}: status {result.get('status_code')}")
            return result

        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return {
                "success": False,
                "error": f"Webhook send failed: {str(e)}",
                "webhook_url": webhook_url
            }

    @tool
    async def api_health_check(self, endpoints: List[str], timeout: int = 10) -> Dict[str, Any]:
        """
        Check health status of multiple API endpoints.

        Args:
            endpoints: List of endpoint URLs to check
            timeout: Timeout for each check in seconds

        Returns:
            Dictionary with health check results
        """
        try:
            results = []
            healthy_count = 0
            unhealthy_count = 0

            for endpoint in endpoints[:20]:  # Limit to 20 endpoints
                try:
                    # Make HEAD request for health check
                    async with aiohttp.ClientSession() as session:
                        async with session.head(
                            endpoint,
                            headers=self.default_headers,
                            timeout=timeout,
                            allow_redirects=True
                        ) as response:
                            is_healthy = 200 <= response.status < 400

                            results.append({
                                "endpoint": endpoint,
                                "status_code": response.status,
                                "status_text": response.reason,
                                "healthy": is_healthy,
                                "response_time_ms": None  # Could add timing
                            })

                            if is_healthy:
                                healthy_count += 1
                            else:
                                unhealthy_count += 1

                except asyncio.TimeoutError:
                    results.append({
                        "endpoint": endpoint,
                        "status_code": None,
                        "status_text": "Timeout",
                        "healthy": False,
                        "error": f"Timeout after {timeout} seconds"
                    })
                    unhealthy_count += 1

                except Exception as e:
                    results.append({
                        "endpoint": endpoint,
                        "status_code": None,
                        "status_text": "Error",
                        "healthy": False,
                        "error": str(e)
                    })
                    unhealthy_count += 1

            logger.info(f"Health check completed: {healthy_count} healthy, {unhealthy_count} unhealthy")

            return {
                "success": True,
                "results": results,
                "summary": {
                    "total": len(results),
                    "healthy": healthy_count,
                    "unhealthy": unhealthy_count,
                    "health_percentage": (healthy_count / len(results) * 100) if results else 0
                }
            }

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "success": False,
                "error": f"Health check failed: {str(e)}"
            }