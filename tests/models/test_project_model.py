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
