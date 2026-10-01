# Sync Requirements Docs

Use this skill whenever implementation changes affect requirements.

## Checklist

1. Identify changed behavior/entities/fields/rules.
2. Update `requirements/Απαιτήσεις_Λογισμικού_Στεγαστικό_v1.md`:
   - bump patch version
   - add changelog entry
   - update impacted sections (functional and/or technical)
3. Update `requirements/Ερωτήσεις_προς_Λειτουργούς.md`:
   - add/adjust open questions for new assumptions
   - keep references/version in sync
4. Update `requirements/Παράδειγμα_Οντοτήτων_Κοινότητα_ΑΒΓ.md`:
   - align entity counts and relationships if model changed
   - add version note
5. Verify all three files use the same version.
6. Summarize exactly what changed in docs in commit/chat notes.
