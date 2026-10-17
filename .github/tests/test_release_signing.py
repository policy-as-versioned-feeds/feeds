"""Exercise the release workflow's real signing call without issuing a signature."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ReleaseSigning(unittest.TestCase):
    def test_actual_tag_call_embeds_rekor_proof(self) -> None:
        workflow = (ROOT / '.github/workflows/cut-release.yml').read_text()
        marker = ('      - name: create the signed annotated tag '
                  '(ambient Actions identity, no interactive login)\n'
                  '        run: |\n')
        self.assertEqual(workflow.count(marker), 1, 'find exactly one real signing step')
        command = textwrap.dedent(workflow.split(marker, 1)[1].split('\n      - ', 1)[0])
        for expression, value in {
                '${{ inputs.feed }}': 'eol', '${{ inputs.version }}': '2.0.0',
                '${{ inputs.message }}': 'synthetic refusing signer probe'}.items():
            command = command.replace(expression, value)
        self.assertNotIn('${{', command)

        with tempfile.TemporaryDirectory(prefix='feed-release-signing-') as temporary:
            root = Path(temporary)
            tools = root / 'bin'
            tools.mkdir()
            record = root / 'signing-mode'
            signer = tools / 'gitsign'
            signer.write_text(
                '#!/bin/sh\nset -eu\n'
                'mode="$(git config --get gitsign.rekorMode || true)"\n'
                'printf "%s\\n" "${mode:-<unset>}" > "$SIGNING_MODE_PROBE"\n'
                'exit 97\n')
            signer.chmod(0o755)
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(('GIT_', 'GITSIGN_', 'SIGSTORE_', 'ACTIONS_'))
                   and not key.endswith('_TOKEN')}
            env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                       GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.hooksPath',
                       GIT_CONFIG_VALUE_0=os.devnull, GITHUB_REPOSITORY_OWNER='synthetic',
                       SIGNING_MODE_PROBE=str(record), PATH=str(tools) + os.pathsep + env['PATH'])

            def git(*arguments: str) -> str:
                return subprocess.check_output(['git', *arguments], cwd=root, env=env,
                                               text=True, stderr=subprocess.DEVNULL).strip()

            git('init', '-q', '-b', 'main')
            git('-c', 'commit.gpgsign=false', '-c', 'user.name=synthetic fixture',
                '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty',
                '-qm', 'synthetic unsigned fixture')
            before = git('rev-parse', 'HEAD')
            result = subprocess.run(['bash', '-c', command], cwd=root, env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, 'the refusing signer must stop the caller')
            self.assertTrue(record.is_file(), result.stderr)
            self.assertEqual(git('rev-parse', 'HEAD'), before)
            self.assertEqual(git('tag'), '', 'the refusing signer must not create a tag')
            self.assertEqual(git('remote'), '', 'the fixture has no publication destination')
            self.assertEqual(record.read_text(), 'offline\n')


if __name__ == '__main__':
    unittest.main()
