# Command: /add-endpoint
Description: Scaffold a complete, vertically integrated FastAPI endpoint following Creonnect architectural boundaries.

## Instructions
When requested to add a new endpoint, follow these strict architectural boundaries systematically:

1. **Domain (`backend/app/domain/`)**: 
   - Define the Pydantic request (e.g., `FeatureRequest`) and response (e.g., `FeatureResponse`) models.
   - Enforce strong typing and validation here.

2. **Service (`backend/app/services/`)**: 
   - Create the business logic orchestration function. 
   - **INVARIANT**: Never put heavy business logic or external API calls directly inside the route definition.

3. **API (`backend/app/api/`)**: 
   - Create the FastAPI route endpoint. 
   - Import the domain models and the service function. 
   - Wire up necessary FastAPI dependencies (e.g., DB sessions, authentication).

4. **Tests (`backend/app/tests/`)**: 
   - Scaffolding isn't done without tests. Create an isolated `pytest` test for this new route, mocking external services.

Always present a summary of the generated/modified files before executing the changes.
