#!/usr/bin/env python
import sys
import os
import shutil
import argparse
import subprocess
import socket
import datetime
import json
import time
import tempfile
import getpass

DATA_DIR = os.environ['MEMO']  # /braintree/data2/active/users/qbilius/memo'


def append_timestamp():
    rec = json.load(open(os.environ['MEMO_DIR'] + 'meta.json', 'r'))
    rec['end_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    json.dump(rec, open(os.environ['MEMO_DIR'] + 'meta.json', 'w'), indent=4)


class Local(object):

    def __init__(self):
        self.args = None
        self.user = getpass.getuser()
        self.host = 'localhost'
        self.executor = 'sh'

        # memo_idx = ''.join(random.SystemRandom().choice(string.ascii_lowercase) for _ in range(4))
        self.memo_idx = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.memo_dir = f'$MEMO/{self.memo_idx}/'
        print('memo id:', self.memo_idx)

    def parser(self, args):
        return args

    def gen_batch_script(self, command):
        script = [command]
        return script


class BrainTree(Local):

    def __init__(self, node='cpu'):
        super().__init__()
        if node.startswith('gpu'):
            num = node[-1]
            node = node[:-1]
        else:
            num = '1'
        self.host = f'braintree-{node}-{num}'


class OpenMind(Local):

    def __init__(self):
        super().__init__()
        self.host = 'openmind7.mit.edu'
        self.executor = 'sbatch'

    def parser(self, args):
        parser = argparse.ArgumentParser()
        parser.add_argument('-t', '--time', default='4-00:00:00')
        parser.add_argument('-n', '--ntasks', default=1, type=int)
        parser.add_argument('-c', '--cpus_per_task', default=5, type=int)
        parser.add_argument('--gpu', default='1080ti:1')
        parser.add_argument('--mem', default='40G')
        parser.add_argument('--qos', action='store_true', default=False)
        parser.add_argument('--jobname', default=None)
        parser.add_argument(
            '--singularity', action='store_true', default=False)
        self.args, script_args = parser.parse_known_args(args)
        return script_args

    def gen_batch_script(self, command):
        script = []
        for k, v in self.args.__dict__.items():
            key = k.replace('_', '-')
            key = f'-{key}' if len(key) == 1 else f'--{key}'

            if k == 'gpu':
                key = '--gres'
                if v.startswith('1080ti'):
                    v = f'gpu:GEFORCEGTX1080TI:{v.split(":")[-1]}'
                else:
                    v = f'gpu:{v}'

            skip = False
            if key == 'qos':
                if v:
                    v = 'dicarlo'
                else:
                    skip = True
            elif key == 'jobname' and v is None:
                skip = True

            if not skip:
                script.append(f'#SBATCH {key}={v}')

        script.append('')
        script.append(f'export MEMO_DIR={self.memo_dir}')
        if self.args.singularity:
            script.append(f'singularity exec --bind /braintree:/braintree '
                          f'--bind /home:/home --bind /om:/om --nv '
                          f'docker://nvidia/cuda:9.0-cudnn7-runtime-centos7 '
                          f'{command}')
        else:
            script.append(command)
        return script


class VSC(Local):

    def __init__(self):
        super().__init__()
        self.user = 'vsc32603'
        self.host = 'login1-tier2.hpc.kuleuven.be'
        self.executor = 'qsub'

    def parser(self, args):
        parser = argparse.ArgumentParser()
        parser.add_argument('-t', '--time', default='4-00:00:00')
        parser.add_argument('-n', '--nodes', default=1, type=int)
        parser.add_argument('--pmem', default='40gb')
        parser.add_argument('--pvmem', default=None)
        parser.add_argument('--ngpus', default=1)
        parser.add_argument('--job_name', default=None)
        self.args, script_args = parser.parse_known_args(args)
        return script_args

    def gen_batch_script(self, command):
        script = []
        for k, v in self.args.__dict__.items():
            key = k.replace('_', '-')

            if k in ['t', 'time']:
                key = 'walltime'
            elif k == 'n':
                nodes = v
            elif k == 'ngpus':
                gpus = v
            elif k == 'job_name':
                key = 'N'

            if key is not None and v is not None:
                script.append(f'#PBS {key}={v}')

        script.append(f'nodes={nodes}:ppn={9 * gpus}:gpus={gpus}')
        script.append('partition=gpu')
        script.append('')
        script.append(f'export MEMO_DIR={self.memo_dir}')
        script.append('')
        script.append(command)
        return script


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable')
    parser.add_argument('script')
    # if sys.argv[1] == 'rmemo' or '--remote' in sys.argv:
    #     parser.add_argument('login')
    parser.add_argument('-t', '--tag', default='')
    parser.add_argument('-d', '--description', default='')
    parser.add_argument('--cluster', choices=['local', 'cpu', 'gpu1', 'gpu2',
                                              'gpu3', 'gpu4', 'om', 'vsc'], default='local')
    parser.add_argument('--remote', action='store_true', default=False)
    parser.add_argument('--keep_cwd', action='store_true', default=False)
    parser.add_argument('--follow', action='store_true', default=False)
    parser.add_argument('--dry', action='store_true', default=False)

    args, extra_args = parser.parse_known_args()
    cluster = CLUSTERS[args.cluster]()
    script_args = cluster.parser(extra_args)

    # Form call command
    if os.path.basename(args.executable) == 'python':
        ex = sys.executable
    else:
        ex = args.executable
    script_args_str = ' '.join(script_args)
    # Add memo_id to the command for easy tracking
    sep = ' -- ' if ' -- ' not in script_args_str else ' '
    command = f'{ex} {args.script} {script_args_str}{sep}--memo_id {cluster.memo_idx}'

    # Prepare run.sh script
    script = ['#!/bin/sh'] + \
        cluster.get_batch_script(command) + ['memo append_timestamp']

    # Define working dir where we will cd to
    if args.remote:
        working_dir = cluster.memo_dir
    else:
        if args.keep_cwd:
            working_dir = os.getcwd()
        else:
            working_dir = os.path.expandvars(cluster.memo_dir)

    # Define what to store in meta.json
    rec = {'start time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
           'full_command': ' '.join(sys.argv),
           'local host': socket.gethostname(),
           'working dir': os.path.abspath(os.getcwd()),
           'remote host': cluster.host,
           'user': cluster.user,
           'cluster args': cluster.args,
           'script args': script_args,
           'outcome': '',
           'show': True}
    rec.update(args.__dict__)

    # Copy everything to memo_dir
    login = f'{cluster.user}@{cluster.host}'
    if not args.dry:
        with tempfile.TemporaryDirectory() as dirname:
            shutil.copy2(sys.argv[2], dirname)
            with open(os.path.join(dirname, 'run.sh'), 'w') as f:
                f.write('\n'.join(script))
            json.dump(rec, open(os.path.join(
                dirname, 'meta.json'), 'w'), indent=4)

            copy_files = ['rsync', '-aq',
                          os.path.join(dirname, '*'), cluster.memo_dir]
            if args.remote:
                copy_files[2] = f'{login}:{copy_files[2]}'
            out = subprocess.run(copy_files, check=True)

    # Call run.sh
    call_args = [cluster.executor, 'run.sh']

    if args.remote:
        bash_cmd = f'cd {working_dir}; ' + ' '.join(call_args)
        call_args = ['ssh', login, 'bash', '--login', '-c', f'"{bash_cmd}"']
        out = subprocess.run(call_args,
                             # open('/dev/null', 'w'),
                             stderr=subprocess.STDOUT,
                             stdout=subprocess.PIPE)
        if args.cluster == 'om':  # print job id
            print(out.stdout.decode('ascii').rstrip('\n'))

    else:
        memo_dir = os.path.expandvars(cluster.memo_dir)

        if not args.follow:
            logfile = os.path.join(memo_dir, 'log.out')
            subprocess.Popen(['nohup'] + call_args, cwd=working_dir,
                             stdin=open('/dev/null', 'w'),
                             stdout=open(logfile, 'a'),
                             stderr=open(logfile, 'a'))
            time.sleep(1)
            subprocess.Popen(['cat', logfile])
        else:
            p = subprocess.Popen(call_args, cwd=working_dir)
            try:
                p.wait()
            except KeyboardInterrupt:
                p.terminate()

    # requests.post('http://localhost:5000/wait-for-changes',
    #               data={'data': db.loc[db.index[-1:]].drop('show', 1).to_html()})


CLUSTERS = {'local': Local,
            'cpu': BrainTree,
            'gpu1': BrainTree,
            'gpu2': BrainTree,
            'gpu3': BrainTree,
            'gpu4': BrainTree,
            'om': OpenMind,
            'vsc': VSC}


if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1] == 'append_timestamp':  # this is called at the end of job
            append_timestamp()
        else:
            main()
