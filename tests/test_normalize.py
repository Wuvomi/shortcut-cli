"""Regression coverage for automatic control-flow normalization."""
import copy
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import shortcut_cli as cli

TEXT_COERCION = {'Type': 'WFCoercionVariableAggrandizement', 'CoercionItemClass': 'WFStringContentItem'}


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        self.workflow = json.loads((ROOT / 'examples' / 'control_flow_normalization.json').read_text(encoding='utf-8'))
        self.actions = self.workflow['WFWorkflowActions']
        self.condition = self.actions[5]['WFWorkflowActionParameters']
        self.menu = self.actions[8]['WFWorkflowActionParameters']
        self.value = self.condition['WFInput']['Variable']['Value']

    def expected(self):
        expected = copy.deepcopy(self.actions)
        expected[5]['WFWorkflowActionParameters']['WFInput']['Variable']['Value']['Aggrandizements'] = [TEXT_COERCION]
        expected[8]['WFWorkflowActionParameters']['WFMenuItems'] = ['New conversation', 'Retry previous turn']
        return expected

    def run_cli(self, *args, language='en'):
        env = dict(os.environ, SHORTCUT_CLI_LANG=language)
        return subprocess.run([sys.executable, str(ROOT / 'shortcut_cli.py'), *map(str, args)],
                              capture_output=True, text=True, env=env, check=True)

    def test_normalizes_only_the_two_expected_fields(self):
        expected = self.expected()
        cli.normalize(self.actions)
        self.assertEqual(self.actions, expected)
        self.assertEqual(self.condition['WFCondition'], 5)
        self.assertEqual(self.actions[10]['WFWorkflowActionParameters']['Text'], 'New-conversation body')
        self.assertEqual(self.actions[12]['WFWorkflowActionParameters']['Text'], 'Retry body')

    def test_existing_explicit_types_and_properties_are_preserved(self):
        for kind in ('WFStringContentItem', 'WFNumberContentItem', 'WFBooleanContentItem', 'WFDateContentItem'):
            with self.subTest(kind=kind):
                self.setUp()
                self.menu['WFMenuItems'] = ['New conversation', 'Retry previous turn']
                self.value['Aggrandizements'] = [
                    {'Type': 'WFPropertyVariableAggrandizement', 'PropertyName': 'Name'},
                    {'Type': 'WFCoercionVariableAggrandizement', 'CoercionItemClass': kind}]
                before = copy.deepcopy(self.actions)
                cli.normalize(self.actions)
                self.assertEqual(self.actions, before)

    def test_property_access_precedes_the_added_text_conversion(self):
        prop = {'Type': 'WFPropertyVariableAggrandizement', 'PropertyName': 'Name'}
        self.value['Aggrandizements'] = [prop]
        cli.normalize(self.actions)
        self.assertEqual(self.value['Aggrandizements'], [prop, TEXT_COERCION])

    def test_ambiguous_conditional_shapes_are_not_retyped(self):
        for case in ('presence', 'numeric', 'unknown', 'output', 'malformed-properties', 'non-text-rhs',
                     'empty-modifier', 'unknown-modifier', 'malformed-property', 'unknown-property-setting'):
            with self.subTest(case=case):
                self.setUp()
                self.menu['WFMenuItems'] = ['New conversation', 'Retry previous turn']
                if case == 'presence': self.condition['WFCondition'] = 100
                if case == 'numeric': self.condition['WFNumberValue'] = 7
                if case == 'unknown': self.condition['FutureConditionalSetting'] = {'opaque': True}
                if case == 'output': self.value['Type'] = 'ActionOutput'
                if case == 'malformed-properties': self.value['Aggrandizements'] = None
                if case == 'non-text-rhs': self.condition['WFConditionalActionString'] = 7
                if case == 'empty-modifier': self.value['Aggrandizements'] = [{}]
                if case == 'unknown-modifier': self.value['Aggrandizements'] = [{'Type': 'FutureVariableModifier'}]
                if case == 'malformed-property':
                    self.value['Aggrandizements'] = [{'Type': 'WFPropertyVariableAggrandizement', 'PropertyName': None}]
                if case == 'unknown-property-setting':
                    self.value['Aggrandizements'] = [{'Type': 'WFPropertyVariableAggrandizement',
                                                     'PropertyName': 'Name', 'FuturePropertySetting': True}]
                before = copy.deepcopy(self.actions)
                cli.normalize(self.actions)
                self.assertEqual(self.actions, before)

    def test_all_text_operators_and_both_rhs_forms_are_preserved(self):
        for operator in (4, 5, 8, 9, 99, 999):
            for token_rhs in (False, True):
                with self.subTest(operator=operator, token_rhs=token_rhs):
                    self.setUp()
                    self.condition['WFCondition'] = operator
                    if not token_rhs:
                        self.condition['WFConditionalActionString'] = "sample 'quoted' 🇨🇭\nline"
                    expected = self.expected()
                    cli.normalize(self.actions)
                    self.assertEqual(self.actions, expected)

    def test_nested_menus_are_normalized_in_their_own_groups(self):
        nested = copy.deepcopy(self.actions[8:])
        for a in nested:
            p = a['WFWorkflowActionParameters']
            p['UUID'] = str(uuid.uuid5(uuid.NAMESPACE_URL, 'nested/' + p['UUID'])).upper()
            if 'GroupingIdentifier' in p:
                p['GroupingIdentifier'] = '355F50CA-FB0E-49C3-8516-629388895994'
        self.actions[10:10] = nested
        cli.normalize(self.actions)
        self.assertEqual(self.menu['WFMenuItems'], ['New conversation', 'Retry previous turn'])
        self.assertEqual(nested[0]['WFWorkflowActionParameters']['WFMenuItems'], self.menu['WFMenuItems'])

    def test_well_formed_nested_conditions_and_repeats_are_preserved(self):
        for kind in ('conditional', 'repeat.count', 'repeat.each'):
            with self.subTest(kind=kind):
                self.setUp()
                group = str(uuid.uuid5(uuid.NAMESPACE_URL, 'nested-control/' + kind)).upper()
                start_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, group + '/start')).upper()
                end_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, group + '/end')).upper()
                params = {'WFControlFlowMode': 0, 'GroupingIdentifier': group, 'UUID': start_uuid}
                if kind == 'conditional':
                    params = copy.deepcopy(self.condition)
                    params.update(GroupingIdentifier=group, UUID=start_uuid)
                    params['WFInput']['Variable']['Value']['Aggrandizements'] = [TEXT_COERCION]
                elif kind == 'repeat.count':
                    params['WFRepeatCount'] = 1
                else:
                    params['WFInput'] = copy.deepcopy(self.condition['WFInput'])
                nested = [
                    {'WFWorkflowActionIdentifier': 'is.workflow.actions.' + kind,
                     'WFWorkflowActionParameters': params},
                    {'WFWorkflowActionIdentifier': 'is.workflow.actions.' + kind,
                     'WFWorkflowActionParameters': {'WFControlFlowMode': 2,
                         'GroupingIdentifier': group, 'UUID': end_uuid}}]
                self.actions[10:10] = nested
                expected = self.expected()
                cli.normalize(self.actions)
                self.assertEqual(self.actions, expected)

    def test_ambiguous_menu_structures_are_not_rewritten(self):
        for case in ('missing-end', 'different-choice', 'dynamic-title', 'reused-group',
                     'unknown-mode', 'duplicate-end', 'orphan-before', 'orphan-after',
                     'unclosed-nested-menu', 'cross-kind-group'):
            with self.subTest(case=case):
                self.setUp()
                actions = copy.deepcopy(self.actions[8:])
                if case == 'missing-end': actions.pop()
                if case == 'different-choice': actions[0]['WFWorkflowActionParameters']['WFMenuItems'].append('Finish')
                if case == 'dynamic-title': actions[0]['WFWorkflowActionParameters']['WFMenuItems'][0] = {'Value': 'dynamic'}
                if case == 'reused-group': actions.insert(1, copy.deepcopy(actions[0]))
                if case == 'unknown-mode':
                    marker = copy.deepcopy(actions[1])
                    marker['WFWorkflowActionParameters']['WFControlFlowMode'] = 3
                    actions.insert(1, marker)
                if case == 'duplicate-end': actions.append(copy.deepcopy(actions[-1]))
                if case == 'orphan-before': actions.insert(0, copy.deepcopy(actions[1]))
                if case == 'orphan-after': actions.append(copy.deepcopy(actions[1]))
                if case == 'unclosed-nested-menu':
                    nested = copy.deepcopy(actions[:2])
                    for marker in nested:
                        marker['WFWorkflowActionParameters']['GroupingIdentifier'] = 'unfinished-nested-menu'
                    actions[2:2] = nested
                if case == 'cross-kind-group':
                    marker = copy.deepcopy(actions[0])
                    marker['WFWorkflowActionIdentifier'] = 'is.workflow.actions.conditional'
                    actions.append(marker)
                before = copy.deepcopy(actions)
                cli.normalize(actions)
                self.assertEqual(actions, before)

    def test_top_level_ids_are_normalized_before_menu_order(self):
        expected = self.expected()
        for a in self.actions:
            p = a['WFWorkflowActionParameters']
            for field in ('UUID', 'GroupingIdentifier'):
                if field in p: a[field] = p.pop(field)
        cli.normalize(self.actions)
        self.assertEqual(self.actions, expected)

    def test_normalization_is_idempotent(self):
        cli.normalize(self.actions)
        before = copy.deepcopy(self.actions)
        cli.normalize(self.actions)
        self.assertEqual(self.actions, before)

    def test_default_compile_and_round_trip_fix_only_known_fields(self):
        with tempfile.TemporaryDirectory() as td:
            first, second, decoded = [Path(td) / name for name in ('first.shortcut', 'second.shortcut', 'decoded.json')]
            fixture = ROOT / 'examples' / 'control_flow_normalization.json'
            compiled = self.run_cli('compile', fixture, '--no-sign', '-o', first)
            self.assertEqual(compiled.stderr, '')
            self.assertEqual(plistlib.loads(first.read_bytes())['WFWorkflowActions'], self.expected())
            self.run_cli('decompile', first, '-o', decoded)
            self.run_cli('compile', decoded, '--no-sign', '-o', second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            verified = self.run_cli('verify', first)
            self.assertIn('unpacked 14 actions', verified.stdout)
            self.assertEqual(verified.stderr, '')
            chinese = self.run_cli('compile', fixture, '--no-sign', '-o', second, language='zh')
            self.assertIn('已编译', chinese.stdout)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertNotIn('--check-authoring', self.run_cli('compile', '--help').stdout)
            self.assertNotIn('--check-authoring', self.run_cli('verify', '--help').stdout)

    def test_bare_actions_list_uses_the_same_default_fix(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td) / 'actions.json', Path(td) / 'actions.shortcut'
            source.write_text(json.dumps(self.actions), encoding='utf-8')
            self.run_cli('compile', source, '--no-sign', '-o', output)
            self.assertEqual(plistlib.loads(output.read_bytes())['WFWorkflowActions'], self.expected())

    def test_decompile_preserves_the_raw_input_without_normalizing(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td) / 'raw.shortcut', Path(td) / 'raw.json'
            source.write_bytes(plistlib.dumps(self.workflow))
            self.run_cli('decompile', source, '-o', output)
            self.assertEqual(json.loads(output.read_text(encoding='utf-8')), self.workflow)


if __name__ == '__main__':
    unittest.main()
