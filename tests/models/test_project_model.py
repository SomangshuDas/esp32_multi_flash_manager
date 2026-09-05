"""Unit tests for app/models/project_model.py."""

from __future__ import annotations

import pytest

from app.models.device_model import DeviceConfig
from app.models.project_model import ProjectModel
from app.utilities.constants import APP_VERSION


class TestProjectModelDeviceOps:
    def test_add_device(self):
        project = ProjectModel()
        device = DeviceConfig(name="Bench 1")
        project.add_device(device)
        assert project.devices == [device]

    def test_remove_device(self):
        project = ProjectModel()
        keep = DeviceConfig(name="Keep")
        drop = DeviceConfig(name="Drop")
        project.add_device(keep)
        project.add_device(drop)
        project.remove_device(drop.id)
        assert project.devices == [keep]

    def test_remove_device_unknown_id_is_noop(self):
        project = ProjectModel()
        device = DeviceConfig()
        project.add_device(device)
        project.remove_device("does-not-exist")
        assert project.devices == [device]

    def test_find_device_returns_match(self):
        project = ProjectModel()
        device = DeviceConfig(name="Findable")
        project.add_device(device)
        found = project.find_device(device.id)
        assert found is device

    def test_find_device_returns_none_when_missing(self):
        project = ProjectModel()
        assert project.find_device("missing-id") is None


class TestProjectModelDefaults:
    def test_default_schema_version_is_current_app_version(self):
        project = ProjectModel()
        assert project.schema_version == APP_VERSION

    def test_default_project_name(self):
        project = ProjectModel()
        assert project.project_name == "Untitled Project"

    def test_devices_default_factory_is_not_shared_between_instances(self):
        a = ProjectModel()
        b = ProjectModel()
        a.add_device(DeviceConfig())
        assert b.devices == []


class TestProjectModelSerialization:
    def test_to_dict_from_dict_roundtrip(self):
        project = ProjectModel(project_name="Line A")
        project.add_device(DeviceConfig(name="Dev 1", com_port="COM3"))
        project.add_device(DeviceConfig(name="Dev 2", com_port="COM4"))
        project.window_geometry_b64 = "Z2VvbWV0cnk="
        project.window_state_b64 = "c3RhdGU="

        restored = ProjectModel.from_dict(project.to_dict())

        assert restored.project_name == "Line A"
        assert restored.schema_version == project.schema_version
        assert len(restored.devices) == 2
        assert {d.name for d in restored.devices} == {"Dev 1", "Dev 2"}
        assert restored.window_geometry_b64 == "Z2VvbWV0cnk="
        assert restored.window_state_b64 == "c3RhdGU="

    def test_from_dict_missing_fields_uses_defaults(self):
        restored = ProjectModel.from_dict({})
        assert restored.project_name == "Untitled Project"
        assert restored.schema_version == APP_VERSION
        assert restored.devices == []
        assert restored.window_geometry_b64 == ""

    def test_from_dict_preserves_older_schema_version_string(self):
        """A project saved by an older release should keep reporting the
        version it was actually saved with, not silently get rewritten to
        the current APP_VERSION on load."""
        restored = ProjectModel.from_dict({"schema_version": "0.1.0"})
        assert restored.schema_version == "0.1.0"

    def test_from_dict_with_malformed_device_entry_raises(self):
        """DeviceConfig.from_dict is defensive about individual fields, but
        a devices list entry that isn't a mapping at all should fail loudly
        rather than silently drop devices -- project_io.py is responsible
        for catching this and reporting a friendly load-failure to the user
        (see tests/project_manager for that boundary)."""
        with pytest.raises(AttributeError):
            ProjectModel.from_dict({"devices": ["not-a-dict"]})


class TestSchemaVersionCheckAndMigration:
    """
    Previously schema_version was written on every save but never read,
    checked, or migrated on load -- pure write-only metadata. These tests
    exercise the two real behaviors added: a forward-compatibility
    warning for files newer than this build, and the migration registry
    mechanism itself.
    """

    def test_older_schema_version_produces_no_warning(self):
        restored = ProjectModel.from_dict({"schema_version": "0.1.0"})
        assert restored.schema_warning == ""

    def test_same_schema_version_produces_no_warning(self):
        restored = ProjectModel.from_dict({"schema_version": APP_VERSION})
        assert restored.schema_warning == ""

    def test_newer_schema_version_produces_a_warning(self):
        newer = f"{int(APP_VERSION.split('.')[0]) + 1}.0.0"
        restored = ProjectModel.from_dict({"schema_version": newer})
        assert restored.schema_warning != ""
        assert newer in restored.schema_warning
        assert APP_VERSION in restored.schema_warning

    def test_schema_warning_is_never_persisted(self):
        newer = f"{int(APP_VERSION.split('.')[0]) + 1}.0.0"
        restored = ProjectModel.from_dict({"schema_version": newer})
        assert "schema_warning" not in restored.to_dict()

    def test_missing_schema_version_defaults_to_current_with_no_warning(self):
        restored = ProjectModel.from_dict({})
        assert restored.schema_warning == ""

    def test_migration_registry_actually_runs(self, monkeypatch):
        """
        Proves the migration mechanism itself executes registered
        migrations for old files, not just that schema_version is stored
        -- there is no real historical schema break to migrate today, so
        this registers a synthetic one for the duration of the test.
        """
        from app.models import project_model as project_model_module

        def _rename_legacy_field(data: dict) -> dict:
            migrated = dict(data)
            if "old_project_name_field" in migrated:
                migrated["project_name"] = migrated.pop("old_project_name_field")
            return migrated

        fake_migrations = [((0, 2, 0), "rename old_project_name_field -> project_name", _rename_legacy_field)]
        monkeypatch.setattr(project_model_module, "_SCHEMA_MIGRATIONS", fake_migrations)

        restored = project_model_module.ProjectModel.from_dict(
            {"schema_version": "0.1.0", "old_project_name_field": "Migrated Name"}
        )
        assert restored.project_name == "Migrated Name"

    def test_migration_does_not_run_for_files_already_at_or_above_threshold(self, monkeypatch):
        from app.models import project_model as project_model_module

        def _should_not_run(data: dict) -> dict:
            migrated = dict(data)
            migrated["project_name"] = "SHOULD NOT APPEAR"
            return migrated

        fake_migrations = [((0, 2, 0), "test migration", _should_not_run)]
        monkeypatch.setattr(project_model_module, "_SCHEMA_MIGRATIONS", fake_migrations)

        restored = project_model_module.ProjectModel.from_dict(
            {"schema_version": "0.2.0", "project_name": "Original Name"}
        )
        assert restored.project_name == "Original Name"
