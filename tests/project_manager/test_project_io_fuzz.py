"""
Fuzz / property-based tests for app/project_manager/project_io.py.

The core guarantee under test: `load_project()` must NEVER raise anything
other than `ProjectLoadError` for ANY file content it's pointed at --
malformed JSON, valid-JSON-but-wrong-shape, deeply nested structures,
huge numbers, null bytes, non-UTF8 bytes, or a hand-crafted "malicious"
.emfm designed to walk into a particular code path. A user should
never be able to crash the app just by double-clicking (or the app
opening) a corrupted or hostile project file.
"""

from __future__ import annotations

import json

from hypothesis import HealthCheck, given, settings, strategies as st

from app.models.project_model import ProjectModel
from app.project_manager.project_io import ProjectLoadError, load_project, save_project

pytestmark = [__import__("pytest").mark.fuzz]

# A recursive JSON-value strategy: bools/ints/floats/strings/None, nested
# inside lists and dicts to arbitrary (bounded) depth.
json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10 ** 18), max_value=10 ** 18),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(max_size=200),
)
json_values = st.recursive(
    json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=8),
        st.dictionaries(st.text(max_size=30), children, max_size=8),
    ),
    max_leaves=40,
)

# Same idea, but always dict-shaped at the top level (closer to a real,
# if corrupted, project file) with a "devices" key that's deliberately
# allowed to be any old JSON value rather than a well-formed list.
fuzzy_project_dict = st.fixed_dictionaries(
    {},
    optional={
        "schema_version": json_values,
        "project_name": json_values,
        "devices": st.one_of(
            json_values,
            st.lists(
                st.one_of(
                    json_values,
                    st.fixed_dictionaries(
                        {},
                        optional={
                            "id": json_values,
                            "name": json_values,
                            "firmware": st.one_of(json_values, st.lists(json_values, max_size=5)),
                            "security": st.one_of(json_values, st.dictionaries(st.text(max_size=20), json_values, max_size=5)),
                            "tags": json_values,
                        },
                    ),
                ),
                max_size=5,
            ),
        ),
        "window_geometry_b64": json_values,
        "window_state_b64": json_values,
    },
)


def _write_emfm(tmp_path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


class TestLoadProjectNeverCrashesOnArbitraryJson:
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(value=json_values)
    def test_arbitrary_top_level_json_value(self, tmp_path, value):
        """Even a JSON document that isn't shaped like a project at all
        (e.g. a bare string, a number, a list of garbage) must be rejected
        cleanly via ProjectLoadError, never an uncaught exception."""
        path = _write_emfm(tmp_path, "fuzz.emfm", json.dumps(value))
        try:
            result = load_project(path)
            assert isinstance(result, ProjectModel)
        except ProjectLoadError:
            pass  # expected outcome for malformed content

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(value=fuzzy_project_dict)
    def test_project_shaped_dict_with_corrupted_fields(self, tmp_path, value):
        """A dict that at least has the right top-level keys, but whose
        values are wrong types (numbers where lists are expected, lists
        where dicts are expected, etc.) must also never crash the loader."""
        path = _write_emfm(tmp_path, "fuzz_shaped.emfm", json.dumps(value))
        try:
            result = load_project(path)
            assert isinstance(result, ProjectModel)
        except ProjectLoadError:
            pass


class TestLoadProjectNeverCrashesOnMalformedText:
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(garbage=st.text(max_size=500))
    def test_arbitrary_non_json_text(self, tmp_path, garbage):
        """Random text (almost certainly not valid JSON) must raise
        ProjectLoadError, never a bare JSONDecodeError or anything else."""
        path = _write_emfm(tmp_path, "garbage.emfm", garbage)
        try:
            load_project(path)
        except ProjectLoadError:
            pass

    def test_empty_file(self, tmp_path):
        path = _write_emfm(tmp_path, "empty.emfm", "")
        try:
            load_project(path)
            assert False, "empty file should not parse as a valid project"
        except ProjectLoadError:
            pass

    def test_truncated_json(self, tmp_path):
        path = _write_emfm(tmp_path, "truncated.emfm", '{"project_name": "Oops", "devices": [')
        try:
            load_project(path)
            assert False, "truncated JSON should not parse"
        except ProjectLoadError:
            pass

    def test_binary_garbage_with_null_bytes(self, tmp_path):
        path = tmp_path / "binary.emfm"
        path.write_bytes(b"\x00\x01\xff\xfe not json at all \x00\x00")
        try:
            load_project(str(path))
            assert False, "binary garbage should not parse as a valid project"
        except ProjectLoadError:
            pass

    def test_deeply_nested_json_does_not_crash_with_recursion_error(self, tmp_path):
        """A maliciously deep nesting structure is a classic DoS/crash
        vector for naive recursive parsers/serializers -- json.load itself
        may raise RecursionError for extreme depths, which must still
        surface as a clean ProjectLoadError, not an uncaught traceback."""
        depth = 5000
        nested = "[" * depth + "]" * depth
        content = f'{{"project_name": "Deep", "devices": {nested}}}'
        path = _write_emfm(tmp_path, "deep.emfm", content)
        try:
            load_project(path)
        except ProjectLoadError:
            pass

    def test_huge_number_does_not_crash(self, tmp_path):
        content = json.dumps({"project_name": "Huge", "devices": [], "schema_version": 10 ** 400})
        path = _write_emfm(tmp_path, "huge.emfm", content)
        result = load_project(path)
        assert isinstance(result, ProjectModel)

    def test_nonexistent_file_raises_load_error_not_os_error(self, tmp_path):
        try:
            load_project(str(tmp_path / "does_not_exist.emfm"))
            assert False, "missing file should raise ProjectLoadError"
        except ProjectLoadError:
            pass
        except OSError:
            raise AssertionError("load_project leaked a raw OSError instead of ProjectLoadError")


class TestSaveThenLoadRoundtripSurvivesFuzzedDeviceData:
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(project_name=st.text(max_size=200), device_name=st.text(max_size=200), tag=st.text(max_size=100))
    def test_arbitrary_unicode_names_roundtrip(self, tmp_path, project_name, device_name, tag):
        """Project/device names and tags are free text -- including
        emoji, control characters, RTL text, etc. -- and must survive a
        save/load roundtrip unchanged rather than corrupting the JSON."""
        from app.models.device_model import DeviceConfig

        project = ProjectModel(project_name=project_name)
        device = DeviceConfig(name=device_name)
        device.tags = [tag]
        project.add_device(device)

        path = tmp_path / "roundtrip.emfm"
        save_project(project, str(path))
        restored = load_project(str(path))

        assert restored.project_name == project_name
        assert restored.devices[0].name == device_name
        assert restored.devices[0].tags == [tag]
