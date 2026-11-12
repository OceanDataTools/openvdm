"""pytest settings for the whole repository (#506).

The Test Setup workers (``server/workers/test_*.py``) match pytest's default
test file names, and the connection-testing functions they import
(``test_cst_source``, ``test_cdt_destination``, ``test_cdt_rclone_destination``)
match its test function names, but none of them are tests. They're ignored
here, relative to this file, so they stay out however pytest is run (e.g.
``python -m pytest server``). The tests are in ``server/tests``.
"""

collect_ignore_glob = ['server/workers/test_*.py']
