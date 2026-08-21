# Command: /check-keys
Description: Run the built-in API keys diagnostic script to verify all external AI and infrastructure services are authenticated.

## Context
Creonnect integrates with Azure OpenAI, standard OpenAI, Gemini, and local infrastructure like Redis. When pipelines fail unexpectedly, it is often due to expired or missing API keys.

## Instructions
1. **Execute Diagnostic Script**: 
   - Run `python check_api_keys.py` located in the repository root.
2. **Analyze Output**: 
   - Review the terminal output to confirm whether all required services (Azure OpenAI, OpenAI, Gemini) report successful authentication.
3. **Resolution**: 
   - If any keys are missing or invalid, inform the user immediately.
   - Direct them to check `.env.example` or `.env.template` for the exact required variable names to update in their local `.env` file.
