"""Tests for swimmer_role pronoun usage rules.

These tests verify that the prompt configuration correctly instructs the LLM
to use 2nd person pronouns when swimmer_role="self" and 3rd person when
swimmer_role="other".

CODEX TASK: Use 2nd-person wording when the user is the swimmer.
"""

import pytest

from app.domain.prompts.base_configs.common import (
    PRONOUN_USAGE_RULES,
    SWIMMER_IDENTIFICATION_RULES,
)
from app.domain.prompts.base_configs.bss import (
    BSS_CONVERSATION_START,
    BSS_LEVEL_PLACEMENT,
    BSSBaseConfig,
)


class TestSwimmerPronounRules:
    """Test cases for swimmer_role pronoun usage."""

    def test_pronoun_rules_section_exists(self):
        """Verify PRONOUN_USAGE_RULES section is defined."""
        assert PRONOUN_USAGE_RULES is not None
        assert len(PRONOUN_USAGE_RULES) > 0

    def test_pronoun_rules_in_bss_config(self):
        """Verify pronoun_usage section is included in BSS config."""
        assert "pronoun_usage" in BSSBaseConfig.sections
        assert BSSBaseConfig.sections["pronoun_usage"] == PRONOUN_USAGE_RULES

    def test_pronoun_rules_in_section_order(self):
        """Verify pronoun_usage appears in the default section order."""
        assert "pronoun_usage" in BSSBaseConfig.default_section_order
        # Should appear after swimmer_identification
        swimmer_idx = BSSBaseConfig.default_section_order.index("swimmer_identification")
        pronoun_idx = BSSBaseConfig.default_section_order.index("pronoun_usage")
        assert pronoun_idx == swimmer_idx + 1

    def test_swimmer_role_self_uses_second_person(self):
        """
        When swimmer_role="self", questions should use 2nd person.

        Example: user_name="Penny", swimmer_role="self" => "How old are you?"
        """
        # Verify the rule explicitly states 2nd person for self
        assert 'swimmer_role = "self"' in PRONOUN_USAGE_RULES or "swimmer_role='self'" in PRONOUN_USAGE_RULES
        assert "2ND PERSON" in PRONOUN_USAGE_RULES or "2nd person" in PRONOUN_USAGE_RULES.lower()
        assert '"How old are you?"' in PRONOUN_USAGE_RULES

    def test_swimmer_role_other_uses_third_person(self):
        """
        When swimmer_role="other", questions should use 3rd person with name.

        Example: swimmer_name="Penny", swimmer_role="other" => "How old is Penny?"
        """
        # Verify the rule explicitly states 3rd person for other
        assert 'swimmer_role = "other"' in PRONOUN_USAGE_RULES or "swimmer_role='other'" in PRONOUN_USAGE_RULES
        assert "3RD PERSON" in PRONOUN_USAGE_RULES or "3rd person" in PRONOUN_USAGE_RULES.lower()

    def test_never_use_name_as_third_person_when_self(self):
        """
        CRITICAL: Never use the user's name as third-person subject when they ARE the swimmer.

        WRONG: "How old is Penny?" when talking TO Penny about herself
        CORRECT: "How old are you?"
        """
        # Check in PRONOUN_USAGE_RULES
        assert "NEVER" in PRONOUN_USAGE_RULES
        assert 'How old is [Name]?" when talking TO that person' in PRONOUN_USAGE_RULES or \
               "How old is Penny?" in PRONOUN_USAGE_RULES

        # Check in BSS_LEVEL_PLACEMENT for the explicit warning
        assert "CRITICAL" in BSS_LEVEL_PLACEMENT
        assert "WRONG when swimmer_role" in BSS_LEVEL_PLACEMENT

    def test_clarification_for_ambiguous_name(self):
        """
        When user provides only a name (e.g., "Penny") without context,
        bot should ask clarification before assuming swimmer_role.
        """
        assert "Clarify" in SWIMMER_IDENTIFICATION_RULES or "clarification" in SWIMMER_IDENTIFICATION_RULES.lower()
        assert "are you the swimmer" in SWIMMER_IDENTIFICATION_RULES.lower()

    def test_level_placement_has_conditional_questions(self):
        """Verify BSS_LEVEL_PLACEMENT has conditional question formats."""
        # Should have both 2nd and 3rd person question examples
        assert 'swimmer_role="self"' in BSS_LEVEL_PLACEMENT
        assert 'swimmer_role="other"' in BSS_LEVEL_PLACEMENT

        # Should have 2nd person questions
        assert '"How old are you?"' in BSS_LEVEL_PLACEMENT
        assert '"Have you had swim lessons before?"' in BSS_LEVEL_PLACEMENT

        # Should have 3rd person questions
        assert '"How old is [swimmer_name]?"' in BSS_LEVEL_PLACEMENT
        assert '"Has [swimmer_name] had swim lessons before?"' in BSS_LEVEL_PLACEMENT

    def test_conversation_start_uses_swimmer_role(self):
        """Verify BSS_CONVERSATION_START references swimmer_role for age question."""
        assert 'swimmer_role="self"' in BSS_CONVERSATION_START
        assert 'swimmer_role="other"' in BSS_CONVERSATION_START
        assert '"How old are you?"' in BSS_CONVERSATION_START
        assert '"How old is [Name]?"' in BSS_CONVERSATION_START

    def test_swimmer_identification_explicit_examples(self):
        """Verify SWIMMER_IDENTIFICATION_RULES has clear examples."""
        # Self example
        assert 'User: "Me"' in SWIMMER_IDENTIFICATION_RULES or "User: \"Me\"" in SWIMMER_IDENTIFICATION_RULES

        # Other example with child
        assert "My son Max" in SWIMMER_IDENTIFICATION_RULES

        # Ambiguous name example requiring clarification
        assert "Penny" in SWIMMER_IDENTIFICATION_RULES

    def test_skill_questions_have_both_forms(self):
        """Verify skill questions exist in both 2nd and 3rd person forms."""
        # 2nd person skill questions
        assert "Are you comfortable" in BSS_LEVEL_PLACEMENT
        assert "Can you float" in BSS_LEVEL_PLACEMENT

        # 3rd person skill questions
        assert "Is [swimmer_name] comfortable" in BSS_LEVEL_PLACEMENT
        assert "Can [swimmer_name] float" in BSS_LEVEL_PLACEMENT


class TestSwimmerIdentificationFlow:
    """Test the swimmer identification conversation flow."""

    def test_opening_question_asks_who_is_swimming(self):
        """First question should ask who will be swimming."""
        assert "Who will be swimming" in BSS_CONVERSATION_START
        assert "you, your child, or someone else" in BSS_CONVERSATION_START

    def test_self_identification_triggers_second_person(self):
        """When user says 'me' or 'I', should use 2nd person."""
        # Check the rules define this flow
        assert "SELF" in SWIMMER_IDENTIFICATION_RULES
        assert "me/I/myself" in SWIMMER_IDENTIFICATION_RULES or \
               "me" in SWIMMER_IDENTIFICATION_RULES.lower()

    def test_child_identification_triggers_third_person(self):
        """When user mentions a child/other person, should use 3rd person."""
        assert "CHILD/OTHER" in SWIMMER_IDENTIFICATION_RULES
        assert "[Name]" in SWIMMER_IDENTIFICATION_RULES or "[swimmer_name]" in SWIMMER_IDENTIFICATION_RULES


class TestPromptIntegration:
    """Integration tests for prompt assembly."""

    def test_all_required_sections_present(self):
        """Verify all swimmer-related sections are in the config."""
        required_sections = [
            "swimmer_identification",
            "pronoun_usage",
            "conversation_start",
            "level_placement",
        ]
        for section in required_sections:
            assert section in BSSBaseConfig.sections, f"Missing section: {section}"
            assert section in BSSBaseConfig.default_section_order, f"Section not in order: {section}"

    def test_get_section_returns_content(self):
        """Verify BSSBaseConfig.get_section works correctly."""
        pronoun_section = BSSBaseConfig.get_section("pronoun_usage")
        assert pronoun_section is not None
        assert "swimmer_role" in pronoun_section

    def test_get_all_sections_includes_pronoun_usage(self):
        """Verify get_all_sections includes the new pronoun_usage section."""
        all_sections = BSSBaseConfig.get_all_sections()
        assert "pronoun_usage" in all_sections
        assert all_sections["pronoun_usage"] == PRONOUN_USAGE_RULES
