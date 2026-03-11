"""
Request transformation functions for different model providers.
These functions transform the standard input format into provider-specific formats.
"""

from typing import Dict, Any, List, Optional
import json

class RequestTransformers:
    """Collection of request transformation functions"""

    @staticmethod
    def add_anthropic_version(data: Dict[str, Any]) -> Dict[str, Any]:
        """Add Anthropic version header to request"""
        data["anthropic_version"] = "bedrock-2023-05-31"
        return data

    @staticmethod
    def format_anthropic_messages(data: Dict[str, Any]) -> Dict[str, Any]:
        """Format messages for Anthropic API"""
        messages = []
        conversation_history = data.get("conversation_history", [])
        
        # Add conversation history
        for msg in conversation_history[-10:]:  # Last 10 messages
            if msg.get("message_type") == "user":
                messages.append({
                    "role": "user",
                    "content": msg.get("content", "")
                })
            elif msg.get("message_type") == "assistant":
                messages.append({
                    "role": "assistant", 
                    "content": msg.get("content", "")
                })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": data["prompt"]
        })
        
        data["messages"] = messages
        return data

    @staticmethod
    def extract_system_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract system prompt from persona context for Anthropic"""
        persona_context = data.get("persona_context", {})
        if persona_context and persona_context.get("system_prompt"):
            data["system"] = persona_context["system_prompt"]
        return data

    @staticmethod
    def add_max_tokens(data: Dict[str, Any]) -> Dict[str, Any]:
        """Add max_tokens parameter"""
        data["max_tokens"] = data.get("max_tokens", 4096)
        return data

    @staticmethod
    def add_temperature(data: Dict[str, Any]) -> Dict[str, Any]:
        """Add temperature parameter"""
        temperature = data.get("temperature", 0.7)
        if temperature != 0.7:  # Only add if different from default
            data["temperature"] = temperature
        return data

    @staticmethod
    def format_deepseek_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
        """Format prompt for DeepSeek models (legacy format)"""
        # Build conversation context
        conversation_text = ""
        conversation_history = data.get("conversation_history", [])
        
        for msg in conversation_history[-10:]:
            if msg.get("message_type") == "user":
                conversation_text += f"User: {msg.get('content', '')}\n"
            elif msg.get("message_type") == "assistant":
                conversation_text += f"Assistant: {msg.get('content', '')}\n"
        
        # Add system prompt if available
        persona_context = data.get("persona_context", {})
        if persona_context and persona_context.get("system_prompt"):
            conversation_text = f"System: {persona_context['system_prompt']}\n\n{conversation_text}"
        
        # Format final prompt
        formatted_prompt = f"{conversation_text}User: {data['prompt']}\nAssistant: "
        data["prompt"] = formatted_prompt
        return data

    @staticmethod
    def format_deepseek_prompt_with_tokens(data: Dict[str, Any]) -> Dict[str, Any]:
        """Format prompt for DeepSeek models with AWS Bedrock special tokens"""
        user_prompt = data["prompt"]
        
        # Let's try without special tokens first to isolate the issue
        # Simple format that should work
        formatted_prompt = user_prompt
        
        data["prompt"] = formatted_prompt
        return data

    @staticmethod
    def add_top_p(data: Dict[str, Any]) -> Dict[str, Any]:
        """Add top_p parameter"""
        top_p = data.get("top_p", 0.9)
        if top_p != 0.9:  # Only add if different from default
            data["top_p"] = top_p
        return data

    @staticmethod
    def add_stop_sequences(data: Dict[str, Any]) -> Dict[str, Any]:
        """Add stop sequences for DeepSeek (optional)"""
        # DeepSeek supports stop sequences, but they're optional
        stop_sequences = data.get("stop", [])
        if stop_sequences and isinstance(stop_sequences, list):
            data["stop"] = stop_sequences[:10]  # Max 10 items per AWS docs
        return data

    @staticmethod
    def format_mistral_messages(data: Dict[str, Any]) -> Dict[str, Any]:
        """Format messages for Mistral Pixtral Large (similar to Anthropic format)"""
        messages = []
        conversation_history = data.get("conversation_history", [])
        
        # Add conversation history
        for msg in conversation_history[-10:]:  # Last 10 messages
            if msg.get("message_type") == "user":
                messages.append({
                    "role": "user",
                    "content": msg.get("content", "")
                })
            elif msg.get("message_type") == "assistant":
                messages.append({
                    "role": "assistant",
                    "content": msg.get("content", "")
                })
        
        # Add current user message
        user_content = data["prompt"]
        
        # Handle multimodal content if images are provided
        if data.get("images"):
            # For multimodal requests, content should be an array
            content_array = [{"text": user_content, "type": "text"}]
            
            # Add images
            for image in data["images"]:
                if isinstance(image, str):  # Base64 encoded image
                    content_array.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image}"
                        }
                    })
            
            messages.append({
                "role": "user",
                "content": content_array
            })
        else:
            # Text-only message
            messages.append({
                "role": "user",
                "content": user_content
            })
        
        data["messages"] = messages
        return data

    @staticmethod
    def format_mistral_converse_messages(data: Dict[str, Any]) -> Dict[str, Any]:
        """Format messages for Mistral Converse API"""
        messages = []
        conversation_history = data.get("conversation_history", [])
        
        # Add conversation history
        for msg in conversation_history[-10:]:
            if msg.get("message_type") == "user":
                messages.append({
                    "role": "user",
                    "content": [{"text": msg.get("content", "")}]
                })
            elif msg.get("message_type") == "assistant":
                messages.append({
                    "role": "assistant",
                    "content": [{"text": msg.get("content", "")}]
                })
        
        # Add current user message
        user_content = [{"text": data["prompt"]}]
        
        # Handle multimodal content for Converse API
        if data.get("images"):
            for image in data["images"]:
                if isinstance(image, bytes):
                    user_content.append({
                        "image": {
                            "format": "png",  # Assume PNG, could be made configurable
                            "source": {
                                "bytes": image
                            }
                        }
                    })
        
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        data["messages"] = messages
        return data

    @staticmethod
    def add_mistral_tools(data: Dict[str, Any]) -> Dict[str, Any]:
        """Add tools for Mistral function calling"""
        tools = data.get("tools", [])
        if tools and isinstance(tools, list):
            data["tools"] = tools
        return data

    @staticmethod
    def format_llama_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
        """Format prompt for Llama models (similar to DeepSeek - uses prompt field)"""
        # Llama models expect a simple prompt format
        # If we have conversation history, format it into the prompt
        conversation_history = data.get("conversation_history", [])
        user_prompt = data["prompt"]
        
        # Build a complete prompt with history
        full_prompt = ""
        
        # Add conversation history in a simple format
        for msg in conversation_history[-5:]:  # Last 5 messages to stay within context
            if msg.get("message_type") == "user":
                full_prompt += f"User: {msg.get('content', '')}\n"
            elif msg.get("message_type") == "assistant":
                full_prompt += f"Assistant: {msg.get('content', '')}\n"
        
        # Add current user message
        full_prompt += f"User: {user_prompt}\nAssistant:"
        
        data["prompt"] = full_prompt
        return data

    @staticmethod
    def add_llama_max_gen_len(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert max_tokens to max_gen_len for Llama models"""
        max_tokens = data.get("max_tokens", 4096)
        data["max_gen_len"] = max_tokens
        # Remove max_tokens as Llama models only accept max_gen_len
        # This prevents ValidationException: extraneous key [max_tokens] is not permitted
        data.pop("max_tokens", None)
        return data

    @staticmethod
    def format_nova_messages(data: Dict[str, Any]) -> Dict[str, Any]:
        """Format messages for Nova models (Converse API)"""
        messages = []
        conversation_history = data.get("conversation_history", [])
        
        # Add conversation history
        for msg in conversation_history[-10:]:
            if msg.get("message_type") == "user":
                messages.append({
                    "role": "user",
                    "content": [{"text": msg.get("content", "")}]
                })
            elif msg.get("message_type") == "assistant":
                messages.append({
                    "role": "assistant",
                    "content": [{"text": msg.get("content", "")}]
                })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": [{"text": data["prompt"]}]
        })
        
        data["messages"] = messages
        return data

    @staticmethod
    def build_inference_config(data: Dict[str, Any]) -> Dict[str, Any]:
        """Build inferenceConfig for Converse API"""
        inference_config = {
            "maxTokens": data.get("max_tokens", 4096)
        }
        
        temperature = data.get("temperature", 0.7)
        if temperature != 0.7:
            inference_config["temperature"] = temperature
            
        top_p = data.get("top_p", 0.9)
        if top_p != 0.9:
            inference_config["topP"] = top_p
            
        data["inferenceConfig"] = inference_config
        return data

    @staticmethod
    def format_openai_messages(data: Dict[str, Any]) -> Dict[str, Any]:
        """Format messages for OpenAI API"""
        messages = []
        conversation_history = data.get("conversation_history", [])
        
        # Add system message from persona context
        persona_context = data.get("persona_context", {})
        if persona_context and persona_context.get("system_prompt"):
            messages.append({
                "role": "system",
                "content": persona_context["system_prompt"]
            })
        
        # Add conversation history
        for msg in conversation_history[-10:]:  # Last 10 messages
            if msg.get("message_type") == "user":
                messages.append({
                    "role": "user",
                    "content": msg.get("content", "")
                })
            elif msg.get("message_type") == "assistant":
                messages.append({
                    "role": "assistant", 
                    "content": msg.get("content", "")
                })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": data["prompt"]
        })
        
        data["messages"] = messages
        return data

    @staticmethod
    def add_openai_model_field(data: Dict[str, Any]) -> Dict[str, Any]:
        """Add model field for OpenAI API (required by OpenAI format)"""
        if "model_id" in data:
            data["model"] = data["model_id"]
        return data

    @staticmethod
    def add_max_completion_tokens(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert max_tokens to max_completion_tokens for OpenAI API"""
        if "max_tokens" in data:
            data["max_completion_tokens"] = data["max_tokens"]
            data.pop("max_tokens", None)
        return data

    @staticmethod
    def remove_unused_fields(data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove fields that shouldn't be sent to the API"""
        # Base fields that should always be removed
        fields_to_remove = [
            "conversation_history", 
            "persona_context", 
            "model_id",
            "stream",
            "userId",
            "session_id",
            "session",
            "model_type_override",  # This was causing the validation error
            "model_config"
        ]
        
        # Model-specific field removal logic
        # If we have messages array, remove prompt (Mistral, Anthropic style)
        # If we have prompt field only, remove messages (DeepSeek, legacy style)
        if "messages" in data and isinstance(data["messages"], list) and len(data["messages"]) > 0:
            # This is a messages-based API (Mistral, Anthropic)
            fields_to_remove.append("prompt")
        elif "prompt" in data and data["prompt"]:
            # This is a prompt-based API (DeepSeek)
            fields_to_remove.append("messages")
        
        for field in fields_to_remove:
            data.pop(field, None)
            
        return data

# Registry of all available transformers
REQUEST_TRANSFORMER_REGISTRY = {
    "add_anthropic_version": RequestTransformers.add_anthropic_version,
    "format_anthropic_messages": RequestTransformers.format_anthropic_messages,
    "extract_system_prompt": RequestTransformers.extract_system_prompt,
    "add_max_tokens": RequestTransformers.add_max_tokens,
    "add_temperature": RequestTransformers.add_temperature,
    "add_top_p": RequestTransformers.add_top_p,
    "add_stop_sequences": RequestTransformers.add_stop_sequences,
    "format_deepseek_prompt": RequestTransformers.format_deepseek_prompt,
    "format_deepseek_prompt_with_tokens": RequestTransformers.format_deepseek_prompt_with_tokens,
    "format_mistral_messages": RequestTransformers.format_mistral_messages,
    "format_mistral_converse_messages": RequestTransformers.format_mistral_converse_messages,
    "add_mistral_tools": RequestTransformers.add_mistral_tools,
    "format_llama_prompt": RequestTransformers.format_llama_prompt,
    "add_llama_max_gen_len": RequestTransformers.add_llama_max_gen_len,
    "format_nova_messages": RequestTransformers.format_nova_messages,
    "build_inference_config": RequestTransformers.build_inference_config,
    "format_openai_messages": RequestTransformers.format_openai_messages,
    "add_openai_model_field": RequestTransformers.add_openai_model_field,
    "add_max_completion_tokens": RequestTransformers.add_max_completion_tokens,
    "remove_unused_fields": RequestTransformers.remove_unused_fields,
}
