"""
AWS Services tools for Strands Agent.
Provides S3, Lambda, and EC2 operations via boto3.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from strands.tools import tool

logger = logging.getLogger(__name__)


class AWSTools:
    """
    AWS Services operation tools for cloud resource management.

    Features:
    - S3: List buckets, get objects
    - Lambda: List functions, invoke functions
    - EC2: Describe instances
    """

    def __init__(self, persona_id: str, credentials: Dict[str, Any]):
        """
        Initialize AWS tools with persona credentials.

        Args:
            persona_id: Unique persona identifier
            credentials: AWS connection credentials:
                - access_key_id: AWS Access Key ID
                - secret_access_key: AWS Secret Access Key
                - region: AWS region (default: us-east-1)
                - role_arn: Optional IAM role to assume
        """
        self.persona_id = persona_id
        self.credentials = credentials
        self.access_key_id = credentials.get("access_key_id", "")
        self.secret_access_key = credentials.get("secret_access_key", "")
        self.region = credentials.get("region", "us-east-1")
        self.role_arn = credentials.get("role_arn", "")

        logger.info(f"AWSTools initialized for persona {persona_id}, region: {self.region}")

    def get_tools(self):
        """Return all AWS operation tools as a list for Strands Agent."""
        return [
            self.list_s3_buckets,
            self.get_s3_object,
            self.list_lambda_functions,
            self.invoke_lambda,
            self.describe_ec2_instances,
            self.test_connection,
        ]

    def _get_session(self):
        """Create a boto3 session with persona credentials."""
        import boto3
        return boto3.Session(
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name=self.region,
        )

    @tool
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test AWS connection by calling STS GetCallerIdentity.

        Returns:
            Dictionary with connection status:
            {
                "success": bool,
                "response_time_ms": float,
                "account_id": str,
                "arn": str,
                "user_id": str,
                "error": Optional[str]
            }
        """
        try:
            import asyncio

            start_time = time.time()

            def _test():
                session = self._get_session()
                sts = session.client("sts")
                return sts.get_caller_identity()

            identity = await asyncio.get_event_loop().run_in_executor(None, _test)
            response_time = round((time.time() - start_time) * 1000)

            return {
                "success": True,
                "response_time_ms": response_time,
                "account_id": identity.get("Account", ""),
                "arn": identity.get("Arn", ""),
                "user_id": identity.get("UserId", ""),
            }

        except Exception as e:
            logger.error(f"AWS connection test failed: {e}", exc_info=True)
            return {"success": False, "error": f"Connection failed: {str(e)}"}

    @tool
    async def list_s3_buckets(self) -> Dict[str, Any]:
        """
        List all S3 buckets accessible with the configured credentials.

        Returns:
            Dictionary with bucket list:
            {
                "success": bool,
                "buckets": List of { name, creation_date },
                "count": int,
                "error": Optional[str]
            }
        """
        try:
            import asyncio

            def _list():
                session = self._get_session()
                s3 = session.client("s3")
                return s3.list_buckets()

            response = await asyncio.get_event_loop().run_in_executor(None, _list)

            buckets = [
                {
                    "name": b["Name"],
                    "creation_date": b["CreationDate"].isoformat() if b.get("CreationDate") else "",
                }
                for b in response.get("Buckets", [])
            ]

            return {"success": True, "buckets": buckets, "count": len(buckets)}

        except Exception as e:
            logger.error(f"Error listing S3 buckets: {e}", exc_info=True)
            return {"success": False, "error": str(e), "buckets": [], "count": 0}

    @tool
    async def get_s3_object(
        self,
        bucket: str,
        key: str,
        max_size: int = 1048576
    ) -> Dict[str, Any]:
        """
        Get an object from S3. Returns text content for text files, metadata for others.

        Args:
            bucket: S3 bucket name
            key: Object key (path) in the bucket
            max_size: Maximum size in bytes to read (default: 1MB). Larger objects return metadata only.

        Returns:
            Dictionary with object content:
            {
                "success": bool,
                "bucket": str,
                "key": str,
                "content": Optional[str] (text content if applicable),
                "content_type": str,
                "size": int,
                "last_modified": str,
                "error": Optional[str]
            }
        """
        try:
            import asyncio

            def _get():
                session = self._get_session()
                s3 = session.client("s3")
                # First get metadata
                head = s3.head_object(Bucket=bucket, Key=key)
                size = head.get("ContentLength", 0)
                content_type = head.get("ContentType", "")
                last_modified = head.get("LastModified")

                content = None
                if size <= max_size and content_type.startswith(("text/", "application/json", "application/xml")):
                    obj = s3.get_object(Bucket=bucket, Key=key)
                    content = obj["Body"].read().decode("utf-8", errors="replace")

                return {
                    "content": content,
                    "content_type": content_type,
                    "size": size,
                    "last_modified": last_modified.isoformat() if last_modified else "",
                }

            result = await asyncio.get_event_loop().run_in_executor(None, _get)

            return {
                "success": True,
                "bucket": bucket,
                "key": key,
                **result,
            }

        except Exception as e:
            logger.error(f"Error getting S3 object: {e}", exc_info=True)
            return {"success": False, "error": str(e), "bucket": bucket, "key": key}

    @tool
    async def list_lambda_functions(
        self,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        List Lambda functions in the configured region.

        Args:
            limit: Maximum functions to return (default: 50, max: 200)

        Returns:
            Dictionary with function list:
            {
                "success": bool,
                "functions": List of { name, runtime, memory, timeout, last_modified, description },
                "count": int,
                "error": Optional[str]
            }
        """
        limit = min(limit, 200)
        try:
            import asyncio

            def _list():
                session = self._get_session()
                lam = session.client("lambda")
                response = lam.list_functions(MaxItems=limit)
                return response.get("Functions", [])

            functions_data = await asyncio.get_event_loop().run_in_executor(None, _list)

            functions = [
                {
                    "name": f["FunctionName"],
                    "runtime": f.get("Runtime", ""),
                    "memory": f.get("MemorySize", 0),
                    "timeout": f.get("Timeout", 0),
                    "last_modified": f.get("LastModified", ""),
                    "description": f.get("Description", "")[:200],
                }
                for f in functions_data
            ]

            return {"success": True, "functions": functions, "count": len(functions)}

        except Exception as e:
            logger.error(f"Error listing Lambda functions: {e}", exc_info=True)
            return {"success": False, "error": str(e), "functions": [], "count": 0}

    @tool
    async def invoke_lambda(
        self,
        function_name: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Invoke a Lambda function and return its response.

        Args:
            function_name: Lambda function name or ARN
            payload: Optional JSON payload to send to the function

        Returns:
            Dictionary with invocation result:
            {
                "success": bool,
                "function_name": str,
                "status_code": int,
                "response": Any (parsed JSON response from Lambda),
                "error": Optional[str]
            }
        """
        try:
            import asyncio
            import json

            def _invoke():
                session = self._get_session()
                lam = session.client("lambda")
                kwargs = {
                    "FunctionName": function_name,
                    "InvocationType": "RequestResponse",
                }
                if payload:
                    kwargs["Payload"] = json.dumps(payload)

                response = lam.invoke(**kwargs)
                result_payload = response["Payload"].read().decode("utf-8")
                return {
                    "status_code": response.get("StatusCode", 0),
                    "response": json.loads(result_payload) if result_payload else None,
                    "function_error": response.get("FunctionError"),
                }

            result = await asyncio.get_event_loop().run_in_executor(None, _invoke)

            if result.get("function_error"):
                return {
                    "success": False,
                    "function_name": function_name,
                    "error": f"Lambda error: {result['function_error']}",
                    "response": result.get("response"),
                }

            return {
                "success": True,
                "function_name": function_name,
                "status_code": result["status_code"],
                "response": result["response"],
            }

        except Exception as e:
            logger.error(f"Error invoking Lambda: {e}", exc_info=True)
            return {"success": False, "error": str(e), "function_name": function_name}

    @tool
    async def describe_ec2_instances(
        self,
        instance_ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Describe EC2 instances in the configured region.

        Args:
            instance_ids: Optional list of specific instance IDs to describe
            filters: Optional filters as {Name: Value} (e.g., {"instance-state-name": "running"})

        Returns:
            Dictionary with instance list:
            {
                "success": bool,
                "instances": List of { id, type, state, public_ip, private_ip, name, launch_time },
                "count": int,
                "error": Optional[str]
            }
        """
        try:
            import asyncio

            def _describe():
                session = self._get_session()
                ec2 = session.client("ec2")
                kwargs = {}
                if instance_ids:
                    kwargs["InstanceIds"] = instance_ids
                if filters:
                    kwargs["Filters"] = [
                        {"Name": k, "Values": [v]} for k, v in filters.items()
                    ]

                response = ec2.describe_instances(**kwargs)
                instances = []
                for reservation in response.get("Reservations", []):
                    for inst in reservation.get("Instances", []):
                        # Get Name tag
                        name = ""
                        for tag in inst.get("Tags", []):
                            if tag["Key"] == "Name":
                                name = tag["Value"]
                                break

                        instances.append({
                            "id": inst["InstanceId"],
                            "type": inst.get("InstanceType", ""),
                            "state": inst.get("State", {}).get("Name", ""),
                            "public_ip": inst.get("PublicIpAddress", ""),
                            "private_ip": inst.get("PrivateIpAddress", ""),
                            "name": name,
                            "launch_time": inst.get("LaunchTime", "").isoformat() if inst.get("LaunchTime") else "",
                        })
                return instances

            instances = await asyncio.get_event_loop().run_in_executor(None, _describe)

            return {"success": True, "instances": instances, "count": len(instances)}

        except Exception as e:
            logger.error(f"Error describing EC2 instances: {e}", exc_info=True)
            return {"success": False, "error": str(e), "instances": [], "count": 0}
