"""Linux /proc disappearance is distinct from inaccessible identity evidence."""
import errno
import pytest
from app import process_identity


def test_process_disappearing_during_stat_read_has_no_live_identity(monkeypatch):
    def vanished(_):raise ProcessLookupError(errno.ESRCH,'No such process')
    monkeypatch.setattr(process_identity.Path,'read_bytes',vanished)
    assert process_identity.linux_identity(123) is None


@pytest.mark.parametrize('error',[PermissionError(errno.EACCES,'denied'),OSError(errno.EIO,'I/O error')])
def test_other_read_failures_are_not_treated_as_exited(monkeypatch,error):
    def fail(_):raise error
    monkeypatch.setattr(process_identity.Path,'read_bytes',fail)
    with pytest.raises(type(error)):process_identity.linux_identity(123)
