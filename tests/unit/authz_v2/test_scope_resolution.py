from types import SimpleNamespace

from authz_v2.core.roles import ScopeType
from authz_v2.resources.scoping import resolve_scope
from models import Hospital, LabUnit, Project


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class DB:
    def __init__(self, values, project_lab=None):
        self.values = values
        self.project_lab = project_lab

    def get(self, model, key):
        return self.values.get((model, key))

    def execute(self, _statement):
        return Result(self.project_lab)


def test_missing_lineage_is_not_implicit_system_scope():
    assert resolve_scope(DB({})) is None
    assert resolve_scope(DB({}), allow_system=True).scope_type is ScopeType.SYSTEM
    assert resolve_scope(DB({}), hospital_id=-1) is None


def test_scope_requires_persisted_active_ancestors():
    inactive = SimpleNamespace(id=4, active=False)
    assert resolve_scope(DB({(Project, 4): inactive}), project_id=4) is None
    project = SimpleNamespace(id=4, active=True)
    lab = SimpleNamespace(id=2, hospital_id=1)
    site = SimpleNamespace(id=9, active=False)
    values = {(Project, 4): project, (LabUnit, 2): lab}
    assert resolve_scope(DB(values, site), project_id=4, lab_unit_id=2) is None
    site.active = True
    scope = resolve_scope(DB(values, site), project_id=4, lab_unit_id=2)
    assert scope.project_lab_unit_id == 9
    assert resolve_scope(DB({}), hospital_id=1) is None
    hospital = SimpleNamespace(id=1)
    assert resolve_scope(DB({(Hospital, 1): hospital}), hospital_id=1).scope_id == 1
