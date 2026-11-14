"""T070 admin listing uses real migrated temporary DB and public task serializers."""
import sqlite3
from contextlib import closing

from fastapi.testclient import TestClient

from app.main import app
from test_dataset_api import data_root, setup_admin, create_user, headers, upload
from test_worker_api import submit


def test_admin_empty_list_and_bounded_query(data_root):
    admin, _ = setup_admin(data_root)
    response = admin.get('/api/v1/admin/jobs')
    assert response.status_code == 200
    assert response.json() == {'items': [], 'total': 0, 'page': 1, 'page_size': 20}
    for query in ('page=0', 'page_size=0', 'page_size=101'):
        assert admin.get('/api/v1/admin/jobs?' + query).status_code == 422


def test_admin_cross_project_stable_pagination_uses_public_fields(data_root):
    admin, project = setup_admin(data_root)
    user = create_user(admin, 'member')
    other = user.post('/api/v1/projects', headers=headers(user), json={'name': 'member-project'}).json()['id']
    jobs = [submit(admin, upload(admin, project).json()['id']),
            submit(user, upload(user, other).json()['id'])]
    with closing(sqlite3.connect(data_root / 'platform.db')) as conn:
        conn.execute("UPDATE jobs SET created_at='2026-11-14T00:00:00+00:00'")
        conn.commit()
    expected = sorted(jobs, reverse=True)
    for page, task in enumerate(expected, 1):
        response = admin.get('/api/v1/admin/jobs', params={'page': page, 'page_size': 1})
        assert response.status_code == 200
        body = response.json()
        assert body['total'] == 2 and body['page'] == page and body['page_size'] == 1
        assert body['items'] == [admin.get(f'/api/v1/jobs/{task}').json()]
        assert not ({'payload_json', 'process_identity_json', 'environment_json', 'input_snapshot_json', 'worker_pid'} & body['items'][0].keys())
    assert admin.get('/api/v1/admin/jobs?page=3&page_size=1').json()['items'] == []
    assert user.get('/api/v1/admin/jobs').status_code == 403
    assert TestClient(app).get('/api/v1/admin/jobs').status_code == 401
    assert user.get(f'/api/v1/jobs/{jobs[0]}').status_code == 404


def test_disabled_admin_session_cannot_list_tasks(data_root):
    admin, _ = setup_admin(data_root)
    with closing(sqlite3.connect(data_root / 'platform.db')) as conn:
        conn.execute("UPDATE users SET is_active=0 WHERE username='root'")
        conn.commit()
    assert admin.get('/api/v1/admin/jobs').status_code == 401
