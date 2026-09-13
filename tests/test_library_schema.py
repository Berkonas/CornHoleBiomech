from pathlib import Path
import runpy
import uuid
import pytest

validate = runpy.run_path(str(Path(__file__).parents[1] / 'scripts/validate_data_schema.py'))['validate_project']


@pytest.mark.parametrize('version', [1, 2, 3])
def test_supported_schema_retains_missing_original_warning(tmp_path, version):
    athlete, trial = str(uuid.uuid4()), str(uuid.uuid4())
    doc = dict(schemaVersion=version, id=str(uuid.uuid4()), athletes=[dict(id=athlete)], trials=[
        dict(id=trial, athleteID=athlete, sourceVideoRelativePath='throws/original.mp4', preparedVideoRelativePath='throws/revisions/prepared.mp4')])
    assert len(validate(doc, tmp_path / 'project.json')) == 1


@pytest.mark.parametrize('path', ['../escape.mp4', '/outside.mp4'])
def test_schema_rejects_prepared_path_escape(tmp_path, path):
    athlete = str(uuid.uuid4())
    doc = dict(schemaVersion=3, id=str(uuid.uuid4()), athletes=[dict(id=athlete)], trials=[
        dict(id=str(uuid.uuid4()), athleteID=athlete, sourceVideoRelativePath='original.mp4', preparedVideoRelativePath=path)])
    with pytest.raises(ValueError, match='inside the library'): validate(doc, tmp_path / 'project.json')


def test_schema_rejects_future_version(tmp_path):
    with pytest.raises(ValueError, match='unsupported'): validate(dict(schemaVersion=999), tmp_path / 'project.json')
