"""
Response transformation functions for different model providers.
These functions extract content and metadata from provider-specific response formats.
"""

from typing import Dict, Any, List, Optional
import json

class ResponseTransformers:
    """Collection of response transformation functions"""

    @staticmethod
    def extract_anthropic_content(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from Anthropic response format"""
        content = ""
        
        # Anthropic response format: {"content": [{"text": "response", "type": "text"}], ...}
        if "content" in response and isinstance(response["content"], list):
            for content_block in response["content"]:
                if content_block.get("type") == "text" and "text" in content_block:
                    content = content_block["text"]
                    break
        
        # Fallback for other formats
        elif "completion" in response:
            content = response["completion"]
        
        response["extracted_content"] = content
        return response

    @staticmethod
    def extract_anthropic_usage(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract token usage from Anthropic response"""
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }
        
        if "usage" in response:
            anthropic_usage = response["usage"]
            usage = {
                "input_tokens": anthropic_usage.get("input_tokens", 0),
                "output_tokens": anthropic_usage.get("output_tokens", 0),
                "total_tokens": anthropic_usage.get("input_tokens", 0) + anthropic_usage.get("output_tokens", 0)
            }
        
        response["extracted_usage"] = usage
        return response

    @staticmethod
    def extract_deepseek_content(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from DeepSeek response format (legacy)"""
        content = ""
        
        if "completion" in response:
            content = response["completion"]
        elif "text" in response:
            content = response["text"]
        elif "choices" in response and len(response["choices"]) > 0:
            content = response["choices"][0].get("text", "")
            
        response["extracted_content"] = content
        return response

    @staticmethod
    def extract_deepseek_choices_content(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from DeepSeek choices format (AWS Bedrock official)"""
        content = ""
        
        # DeepSeek AWS Bedrock format: {"choices": [{"text": "...", "stop_reason": "..."}]}
        if "choices" in response and isinstance(response["choices"], list) and len(response["choices"]) > 0:
            choice = response["choices"][0]
            raw_content = choice.get("text", "")
            
            # Clean up DeepSeek content for frontend consistency
            content = ResponseTransformers._clean_deepseek_content(raw_content)
            
        # Fallback to other formats
        elif "completion" in response:
            content = response["completion"]
        elif "text" in response:
            content = response["text"]
            
        response["extracted_content"] = content
        return response

    @staticmethod
    def _clean_deepseek_content(raw_content: str) -> str:
        """Clean and standardize DeepSeek content for frontend"""
        if not raw_content:
            return ""
        
        # Remove excessive Windows line endings and normalize
        content = raw_content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove leading/trailing whitespace
        content = content.strip()
        
        # If content starts with newlines, remove them
        while content.startswith('\n'):
            content = content[1:]
        
        # If the content is very long and seems to contain multiple Q&A pairs,
        # try to extract just the first meaningful response
        lines = content.split('\n')
        if len(lines) > 10:  # If response is very long
            # Look for the first substantial answer (usually the first few lines)
            meaningful_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('What is') and not line.startswith('How do'):
                    meaningful_lines.append(line)
                    # Stop if we have a complete answer (ends with period, question mark, etc.)
                    if line.endswith('.') or line.endswith('!') or line.endswith('?'):
                        # Check if this looks like a complete answer
                        combined = ' '.join(meaningful_lines)
                        if len(combined) > 50:  # Reasonable answer length
                            break
            
            if meaningful_lines:
                content = ' '.join(meaningful_lines)
        
        return content

    @staticmethod
    def extract_deepseek_usage(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract token usage from DeepSeek response"""
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }
        
        # Check for usage in different possible locations
        if "usage" in response:
            deepseek_usage = response["usage"]
            usage = {
                "input_tokens": deepseek_usage.get("prompt_tokens", deepseek_usage.get("input_tokens", 0)),
                "output_tokens": deepseek_usage.get("completion_tokens", deepseek_usage.get("output_tokens", 0)),
                "total_tokens": deepseek_usage.get("total_tokens", 0)
            }
        elif "choices" in response and len(response["choices"]) > 0:
            # Sometimes usage might be in the choice object
            choice = response["choices"][0]
            if "usage" in choice:
                choice_usage = choice["usage"]
                usage = {
                    "input_tokens": choice_usage.get("prompt_tokens", choice_usage.get("input_tokens", 0)),
                    "output_tokens": choice_usage.get("completion_tokens", choice_usage.get("output_tokens", 0)),
                    "total_tokens": choice_usage.get("total_tokens", 0)
                }
        
        # If no usage found, estimate based on content length (rough approximation)
        if usage["total_tokens"] == 0 and "extracted_content" in response:
            content = response["extracted_content"]
            if content:
                # Rough estimation: ~4 characters per token
                estimated_output_tokens = len(content) // 4
                usage = {
                    "input_tokens": 0,  # We don't have input token count
                    "output_tokens": estimated_output_tokens,
                    "total_tokens": estimated_output_tokens
                }
            
        response["extracted_usage"] = usage
        return response

    @staticmethod
    def extract_nova_content(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from Nova Converse API response"""
        content = ""
        
        # Nova Converse response format
        if "output" in response and "message" in response["output"]:
            message = response["output"]["message"]
            if "content" in message and len(message["content"]) > 0:
                first_content = message["content"][0]
                if "text" in first_content:
                    content = first_content["text"]
                    
        response["extracted_content"] = content
        return response

    @staticmethod
    def extract_nova_usage(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract token usage from Nova response"""
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }
        
        if "usage" in response:
            nova_usage = response["usage"]
            usage = {
                "input_tokens": nova_usage.get("inputTokens", 0),
                "output_tokens": nova_usage.get("outputTokens", 0),
                "total_tokens": nova_usage.get("totalTokens", 0)
            }
            
        response["extracted_usage"] = usage
        return response

    @staticmethod
    def extract_streaming_anthropic_content(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from Anthropic streaming chunk"""
        content = ""
        
        # Check for Anthropic streaming format
        if "delta" in chunk and "text" in chunk["delta"]:
            content = chunk["delta"]["text"]
        elif "content_block_delta" in chunk:
            delta = chunk["content_block_delta"]
            if "delta" in delta and "text" in delta["delta"]:
                content = delta["delta"]["text"]
        elif "completion" in chunk:
            content = chunk["completion"]
            
        chunk["extracted_content"] = content
        return chunk

    @staticmethod
    def extract_streaming_deepseek_content(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from DeepSeek streaming chunk (legacy)"""
        content = ""
        
        if "choices" in chunk and isinstance(chunk["choices"], list) and len(chunk["choices"]) > 0:
            choice = chunk["choices"][0]
            if "text" in choice:
                content = choice["text"]
        elif "completion" in chunk:
            content = chunk["completion"]
        elif "text" in chunk:
            content = chunk["text"]
            
        chunk["extracted_content"] = content
        return chunk

    @staticmethod
    def extract_streaming_deepseek_choices_content(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from DeepSeek streaming choices format (AWS Bedrock official)"""
        content = ""
        
        # DeepSeek streaming format: {"choices": [{"text": "chunk", "stop_reason": null}]}
        if "choices" in chunk and isinstance(chunk["choices"], list) and len(chunk["choices"]) > 0:
            choice = chunk["choices"][0]
            if "text" in choice:
                content = str(choice["text"])
        elif "completion" in chunk:
            content = chunk["completion"]
        elif "text" in chunk:
            content = chunk["text"]
            
        chunk["extracted_content"] = content
        return chunk

    @staticmethod
    def detect_completion_anthropic(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if Anthropic streaming is complete"""
        is_complete = False
        
        if chunk.get("type") == "message_stop":
            is_complete = True
        elif "stop_reason" in chunk:
            is_complete = True
        elif chunk.get("type") == "content_block_stop":
            is_complete = True
            
        chunk["is_complete"] = is_complete
        return chunk

    @staticmethod
    def detect_completion_deepseek(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if DeepSeek streaming is complete"""
        is_complete = False
        
        if "stop_reason" in chunk:
            is_complete = True
        elif chunk.get("type") == "completion":
            is_complete = True
        elif "completionReason" in chunk:
            is_complete = True
            
        chunk["is_complete"] = is_complete
        return chunk

    @staticmethod
    def extract_streaming_nova_content(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from Nova Converse streaming chunk"""
        content = ""
        
        # Check for Nova Converse streaming format
        if 'contentBlockDelta' in chunk:
            delta = chunk['contentBlockDelta']['delta']
            if 'text' in delta:
                content = delta['text']
        elif 'messageStop' in chunk:
            # This is the final chunk, no content
            content = ""
            
        chunk["extracted_content"] = content
        return chunk

    @staticmethod
    def detect_completion_nova(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if Nova Converse streaming is complete"""
        is_complete = False
        
        if 'messageStop' in chunk:
            is_complete = True
        elif chunk.get("type") == "messageStop":
            is_complete = True
            
        chunk["is_complete"] = is_complete
        return chunk

    @staticmethod
    def extract_mistral_content(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from Mistral response format"""
        content = ""
        
        # Mistral response format: {"choices": [{"message": {"content": "...", "role": "assistant"}}]}
        if "choices" in response and isinstance(response["choices"], list) and len(response["choices"]) > 0:
            choice = response["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                content = choice["message"]["content"]
        
        # Fallback formats
        elif "content" in response:
            content = response["content"]
        elif "text" in response:
            content = response["text"]
            
        response["extracted_content"] = content
        return response

    @staticmethod
    def extract_mistral_usage(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract token usage from Mistral response"""
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }
        
        # Check for usage in response
        if "usage" in response:
            mistral_usage = response["usage"]
            usage = {
                "input_tokens": mistral_usage.get("prompt_tokens", mistral_usage.get("input_tokens", 0)),
                "output_tokens": mistral_usage.get("completion_tokens", mistral_usage.get("output_tokens", 0)),
                "total_tokens": mistral_usage.get("total_tokens", 0)
            }
        elif "choices" in response and len(response["choices"]) > 0:
            # Sometimes usage might be in the choice object
            choice = response["choices"][0]
            if "usage" in choice:
                choice_usage = choice["usage"]
                usage = {
                    "input_tokens": choice_usage.get("prompt_tokens", choice_usage.get("input_tokens", 0)),
                    "output_tokens": choice_usage.get("completion_tokens", choice_usage.get("output_tokens", 0)),
                    "total_tokens": choice_usage.get("total_tokens", 0)
                }
        
        # If no usage found, estimate based on content length
        if usage["total_tokens"] == 0 and "extracted_content" in response:
            content = response["extracted_content"]
            if content:
                estimated_output_tokens = len(content) // 4
                usage = {
                    "input_tokens": 0,
                    "output_tokens": estimated_output_tokens,
                    "total_tokens": estimated_output_tokens
                }
            
        response["extracted_usage"] = usage
        return response

    @staticmethod
    def extract_streaming_mistral_content(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from Mistral streaming chunk"""
        content = ""
        
        # Mistral streaming format: {"choices": [{"delta": {"content": "chunk"}}]}
        if "choices" in chunk and isinstance(chunk["choices"], list) and len(chunk["choices"]) > 0:
            choice = chunk["choices"][0]
            if "delta" in choice and "content" in choice["delta"]:
                content = choice["delta"]["content"]
        elif "content" in chunk:
            content = chunk["content"]
        elif "text" in chunk:
            content = chunk["text"]
            
        chunk["extracted_content"] = content
        return chunk

    @staticmethod
    def detect_completion_mistral(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if Mistral streaming is complete"""
        is_complete = False
        
        # Check for Mistral completion indicators
        if "choices" in chunk and len(chunk["choices"]) > 0:
            choice = chunk["choices"][0]
            if choice.get("finish_reason"):
                is_complete = True
        elif "finish_reason" in chunk:
            is_complete = True
        elif chunk.get("type") == "done":
            is_complete = True
            
        chunk["is_complete"] = is_complete
        return chunk

    @staticmethod
    def extract_llama_content(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from Llama response format"""
        content = ""
        
        # Llama response format: {"generation": "text content"}
        if "generation" in response:
            content = response["generation"]
        elif "text" in response:
            content = response["text"]
        elif "content" in response:
            content = response["content"]
        
        # Clean up the content - remove any "Assistant:" prefix if present
        if content.startswith("Assistant:"):
            content = content[10:].strip()
            
        response["extracted_content"] = content
        return response

    @staticmethod
    def extract_llama_usage(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract token usage from Llama response"""
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }
        
        # Llama might have usage information
        if "usage" in response:
            llama_usage = response["usage"]
            usage = {
                "input_tokens": llama_usage.get("prompt_tokens", llama_usage.get("input_tokens", 0)),
                "output_tokens": llama_usage.get("completion_tokens", llama_usage.get("output_tokens", 0)),
                "total_tokens": llama_usage.get("total_tokens", 0)
            }
        
        # If no usage found, estimate based on content length
        if usage["total_tokens"] == 0 and "extracted_content" in response:
            content = response["extracted_content"]
            if content:
                estimated_output_tokens = len(content) // 4
                usage = {
                    "input_tokens": 0,
                    "output_tokens": estimated_output_tokens,
                    "total_tokens": estimated_output_tokens
                }
            
        response["extracted_usage"] = usage
        return response

    @staticmethod
    def extract_streaming_llama_content(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from Llama streaming chunk"""
        content = ""
        
        # Llama streaming format may vary, check common patterns
        if "generation" in chunk:
            content = chunk["generation"]
        elif "text" in chunk:
            content = chunk["text"]
        elif "content" in chunk:
            content = chunk["content"]
        elif "delta" in chunk:
            content = chunk["delta"]
            
        chunk["extracted_content"] = content
        return chunk

    @staticmethod
    def detect_completion_llama(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if Llama streaming is complete"""
        is_complete = False
        
        # Check for Llama completion indicators
        if chunk.get("stop_reason"):
            is_complete = True
        elif chunk.get("finish_reason"):
            is_complete = True
        elif chunk.get("type") == "generation_stopped":
            is_complete = True
        elif chunk.get("generation_complete"):
            is_complete = True
            
        chunk["is_complete"] = is_complete
        return chunk

    @staticmethod
    def extract_openai_content(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from OpenAI response format"""
        content = ""
        
        # OpenAI response format: {"choices": [{"message": {"content": "response"}}]}
        if "choices" in response and isinstance(response["choices"], list) and len(response["choices"]) > 0:
            choice = response["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                content = choice["message"]["content"]
        
        response["extracted_content"] = content
        return response

    @staticmethod
    def extract_openai_usage(response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract token usage from OpenAI response"""
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }
        
        if "usage" in response:
            openai_usage = response["usage"]
            usage = {
                "input_tokens": openai_usage.get("prompt_tokens", 0),
                "output_tokens": openai_usage.get("completion_tokens", 0),
                "total_tokens": openai_usage.get("total_tokens", 0)
            }
        
        response["extracted_usage"] = usage
        return response

    @staticmethod
    def extract_streaming_openai_content(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from OpenAI streaming response chunk"""
        content = ""
        
        # OpenAI streaming format: {"choices": [{"delta": {"content": "text"}}]}
        if "choices" in chunk and isinstance(chunk["choices"], list) and len(chunk["choices"]) > 0:
            choice = chunk["choices"][0]
            if "delta" in choice and "content" in choice["delta"]:
                content = choice["delta"]["content"]
        
        chunk["extracted_content"] = content
        return chunk

    @staticmethod
    def detect_completion_openai(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Detect if OpenAI streaming is complete"""
        is_complete = False
        
        # OpenAI streaming completion: {"choices": [{"finish_reason": "stop"}]}
        if "choices" in chunk and isinstance(chunk["choices"], list) and len(chunk["choices"]) > 0:
            choice = chunk["choices"][0]
            finish_reason = choice.get("finish_reason")
            if finish_reason in ["stop", "length", "content_filter"]:
                is_complete = True
            
        chunk["is_complete"] = is_complete
        return chunk

    @staticmethod
    def normalize_response(response: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize response to standard format"""
        normalized = {
            "content": response.get("extracted_content", ""),
            "usage": response.get("extracted_usage", {
                "input_tokens": 0,
                "output_tokens": 0, 
                "total_tokens": 0
            }),
            "model_id": response.get("model_id", "unknown"),
            "timestamp": response.get("timestamp", ""),
            "raw_response": response  # Keep original for debugging
        }
        
        return normalized

# Registry of all available transformers
RESPONSE_TRANSFORMER_REGISTRY = {
    "extract_anthropic_content": ResponseTransformers.extract_anthropic_content,
    "extract_anthropic_usage": ResponseTransformers.extract_anthropic_usage,
    "extract_deepseek_content": ResponseTransformers.extract_deepseek_content,
    "extract_deepseek_choices_content": ResponseTransformers.extract_deepseek_choices_content,
    "extract_deepseek_usage": ResponseTransformers.extract_deepseek_usage,
    "extract_mistral_content": ResponseTransformers.extract_mistral_content,
    "extract_mistral_usage": ResponseTransformers.extract_mistral_usage,
    "extract_llama_content": ResponseTransformers.extract_llama_content,
    "extract_llama_usage": ResponseTransformers.extract_llama_usage,
    "extract_nova_content": ResponseTransformers.extract_nova_content,
    "extract_nova_usage": ResponseTransformers.extract_nova_usage,
    "extract_openai_content": ResponseTransformers.extract_openai_content,
    "extract_openai_usage": ResponseTransformers.extract_openai_usage,
    "extract_streaming_anthropic_content": ResponseTransformers.extract_streaming_anthropic_content,
    "extract_streaming_deepseek_content": ResponseTransformers.extract_streaming_deepseek_content,
    "extract_streaming_deepseek_choices_content": ResponseTransformers.extract_streaming_deepseek_choices_content,
    "extract_streaming_mistral_content": ResponseTransformers.extract_streaming_mistral_content,
    "extract_streaming_llama_content": ResponseTransformers.extract_streaming_llama_content,
    "extract_streaming_nova_content": ResponseTransformers.extract_streaming_nova_content,
    "extract_streaming_openai_content": ResponseTransformers.extract_streaming_openai_content,
    "detect_completion_anthropic": ResponseTransformers.detect_completion_anthropic,
    "detect_completion_deepseek": ResponseTransformers.detect_completion_deepseek,
    "detect_completion_mistral": ResponseTransformers.detect_completion_mistral,
    "detect_completion_llama": ResponseTransformers.detect_completion_llama,
    "detect_completion_nova": ResponseTransformers.detect_completion_nova,
    "detect_completion_openai": ResponseTransformers.detect_completion_openai,
    "normalize_response": ResponseTransformers.normalize_response,
}
