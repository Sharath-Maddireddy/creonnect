# Command: /migrate
Description: Autogenerate, review, and apply SQLAlchemy/Alembic database migrations safely.

## Context
Alembic's autogenerate feature is powerful but can sometimes accidentally drop tables, ignore enum changes, or misinterpret renaming as drop/create operations. This command ensures a safe migration workflow.

## Instructions
When requested to create or apply a database migration:

1. **Analyze Models**: Ensure the user's requested SQLAlchemy model changes in `backend/app/models/` (or `backend/app/infra/database.py`) have been saved.
2. **Generate Revision**: Execute the shell command: 
   `alembic revision --autogenerate -m "<User's description>"`
3. **Review (CRITICAL STEP)**: 
   - Read the newly generated migration file in `alembic/versions/`.
   - Verify it only contains the intended changes. 
   - Ensure it didn't accidentally drop unrelated tables or columns.
   - Fix the migration file manually if Alembic made incorrect assumptions.
4. **Apply**: 
   - If the revision is safe, apply it by running: `alembic upgrade head` (or `python run_migration.py`).
   - Confirm success by reading the output.
