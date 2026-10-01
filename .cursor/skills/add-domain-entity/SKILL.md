# Add Domain Entity

Use this skill for introducing or modifying a core domain entity.

## Steps

1. Map the entity to specification section(s).
2. Implement/update model inheriting from audited base model.
3. Add constraints, choices, and indexes matching business rules.
4. Create migration.
5. Register/admin integration (if managed by back office).
6. Add history visibility path (record-level and aggregate where required).
7. Add tests for:
   - creation/update audit records
   - key validations/constraints
   - related workflow effects
8. Sync requirements markdown documents.
