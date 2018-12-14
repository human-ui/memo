#!/usr/bin/env python
import os
import sys
import shutil
import argparse
import subprocess
import socket
import datetime
import json
import time
import tempfile
import getpass


DATA_DIR = os.environ['MEMO']
DB_USERNAME = 'qbilius'
DB_HOST = 'braintree.mit.edu'


# def requires_memoid(func):
#     """
#     Checks if MEMO_DIR is present in environment.
#     If not, the calling function does nothing.
#     """
#     def func_wrapper(*args, **kwargs):
#         if os.getenv('MEMO_DIR') is not None:
#             func(*args, **kwargs)
#     return func_wrapper


def host_from_ip():
    """
    From: https://stackoverflow.com/a/166589
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    host, cluster = IPS.get(ip, 'localhost')
    s.close()
    if cluster == 'braintree':
        node = ''.join(host.split('.')[0].split('-')[1:3])
    else:
        node = None
    return host, cluster, node


def watch_and_sync(local_memo_dir):
    db_memo = get_db_env_var('MEMO')
    memo_id = get_memo_id(local_memo_dir)
    db_memo_dir = os.path.join(db_memo, memo_id)
    last_update = 0
    while True:
        time.sleep(5)
        this_update = os.path.getmtime(local_memo_dir)
        if this_update > last_update:
            last_update = this_update
            sync(local_memo_dir, db_memo_dir)


def get_db_env_var(varname):
    command = f'"echo ${varname}"'
    out = subprocess.run(['ssh', f'{DB_USERNAME}@{DB_HOST}',
                            'bash', '--login', '-c', command],
                            stderr=subprocess.STDOUT,
                            stdout=subprocess.PIPE)
    # out.stdout.decode('ascii')
    # out = subprocess.check_output(['ssh', f'{DB_USERNAME}@{DB_HOST}',
    #                                 f"sh -l -c 'echo ${varname}'"])
    # import ipdb; ipdb.set_trace()
    var = out.stdout.decode('ascii').split('\n')[-2]
    return var


def get_memo_id(local_memo_dir):
    rec = json.load(open(os.path.join(local_memo_dir, 'meta.json'), 'r'))
    return rec['memo_id']


def sync(src, dst):
    subprocess.Popen(['rsync', '-aq', f'{src}/',
                      f'{DB_USERNAME}@{DB_HOST}:{dst}']).wait()


def on_exit(local_memo_dir):
    """
    Appends end time stamp after the process is over and syncing to db
    """
    meta_path = os.path.join(local_memo_dir, 'meta.json')
    try:
        rec = json.load(open(meta_path, 'r'))
    except:
        time.sleep(1)
        rec = json.load(open(meta_path, 'r'))
    rec['end_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    json.dump(rec, open(meta_path, 'w'), indent=4)

    db_memo = get_db_env_var('MEMO')
    memo_id = get_memo_id(local_memo_dir)
    db_memo_dir = os.path.join(db_memo, memo_id)
    sync(local_memo_dir, db_memo_dir)





# def watch_and_sync():
#     observer = watchdog.observers.Observer()
#     observer.schedule(event_handler, self.DIRECTORY_TO_WATCH, recursive=True)
#     observer.start()


# class Handler(watchdog.events.FileSystemEventHandler):

#     @staticmethod
#     def on_any_event(event):
#         sync()



# @requires_memoid
# def sync():
#     """
#     Used for syncing files from local storage to remote
#     """
#     memo_id = os.path.basename(os.environ['MEMO_DIR'])
#     remote_memo = get_db_env_var('MEMO')
#     remote_memo_dir = os.path.join(remote_memo, memo_id)
#     subprocess.Popen(['rsync', '-aP', os.environ['MEMO_DIR'],
#                       f'qbilius@braintree.mit.edu:{remote_memo_dir}'])


class Local(object):

    host = 'localhost'
    executor = 'sh'

    def __init__(self, user=None):
        self.user = getpass.getuser() if user is None else user

        self.args = None

        # memo_idx = ''.join(random.SystemRandom().choice(string.ascii_lowercase) for _ in range(4))
        self.memo_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

        local_host, cluster, node = host_from_ip()
        if local_host == self.host:
            self.memo_dir = tempfile.mkdtemp()
        else:
            command = 'python -c '+ "'import tempfile; print(tempfile.mkdtemp())'"
            out = self.exec_remote(command)
            self.memo_dir = out.split('\n')[-2]
        print('memo id:', self.memo_id)
        # self.memo_dir = f'$MEMO/{self.memo_idx}/'
        # os.environ['MEMO_ID'] = self.memo_id
        # os.environ['MEMO_DIR'] = self.memo_dir

    def parser(self, args):
        return args

    def gen_batch_script(self, command, prefix=''):
        script = ['#!/bin/sh',
                  prefix,
                  f'export MEMO_DIR={self.memo_dir}',
                  f'nohup memo watch_and_sync {self.memo_dir} -- --memo_id {self.memo_id} &',
                  'WATCH_PID=$!',
                  command,
                  'kill $WATCH_PID',
                  f'memo on_exit {self.memo_dir}']
        return script

    def exec_remote(self, command):
        out = subprocess.run(['ssh', f'{self.user}@{self.host}',
                            'bash', '--login', '-c', command],
                            stderr=subprocess.STDOUT,
                            stdout=subprocess.PIPE)
        return out.stdout.decode('ascii')


class BrainTree(Local):

    executor = 'sh'

    def __init__(self, user=None, node='cpu'):
        if node.startswith('gpu'):
            num = node[-1]
            node = node[:-1]
        else:
            num = '1'
        self.host = f'braintree-{node}-{num}.mit.edu'
        super().__init__(user=user)


class OpenMind(Local):

    host = 'openmind7.mit.edu'
    executor = 'sbatch'

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

    host = 'login1-tier2.hpc.kuleuven.be',
    executor = 'qsub'

    def __init__(self, user='vsc32603'):
        super().__init__(user=user)

    def parser(self, args):
        parser = argparse.ArgumentParser()
        parser.add_argument('--time', default='4:00:00:00')
        parser.add_argument('--nodes', default=1, type=int)
        parser.add_argument('--pmem', default='40gb')
        parser.add_argument('--pvmem', default=None)
        parser.add_argument('--gpus', default=1, type=int)
        # parser.add_argument('--qos', default='q72h')
        parser.add_argument('-N', '--job_name', default=None)
        parser.add_argument('-A', '--project_name', default='default_project')
        self.args, script_args = parser.parse_known_args(args)
        return script_args

    def gen_batch_script(self, command):
        l_options = ['time', 'pmem', 'pvmem', 'qos']
        l_list = []
        pbs = []
        for k, v in self.args.__dict__.items():
            # k = k.replace('_', '-')
            option = None
            if k in l_options:
                if k == 'time':
                    l_list.append(f'walltime={v}')
                elif v is not None:
                    l_list.append(f'{k}={v}')
            elif k == 'nodes':
                nodes = v
            elif k == 'gpus':
                gpus = v
            elif k == 'job_name':
                option = f'-N {v}'
            elif k == 'project_name':
                # if v is not None:
                option = f'-A {v}'
            else:
                raise ValueError(f'Option {k} with value {v} not recognized.')

            if option is not None and v is not None:
                pbs.append(option)

        l_list += [f'nodes={nodes}:ppn={9 * gpus}:gpus={gpus}',
                   'partition=gpu']
        pbs.append('-l ' + ",".join(l_list))
        pbs = ' '.join(pbs)

        script = []
        script.append(f'#PBS {pbs}')
        script.append('')
        script.append(f'export MEMO_DIR={self.memo_dir}')
        script.append('cd $MEMO_DIR')
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
    parser.add_argument('--cluster', choices=['local', 'braintree', 'om', 'vsc'])
    parser.add_argument('--node', default='gpu3')
    # parser.add_argument('--remote', action='store_true', default=False)
    parser.add_argument('--keep_cwd', action='store_true', default=False)
    parser.add_argument('--follow', action='store_true', default=False)
    parser.add_argument('--dry', action='store_true', default=False)

    args, extra_args = parser.parse_known_args()
    local_host, cluster, node = host_from_ip()
    if args.cluster is None:
        args.cluster = cluster
        args.node = node

    cluster = CLUSTERS[args.cluster]
    if args.cluster == 'braintree':
        cluster = cluster(node=args.node)
    else:
        cluster = cluster()
    script_args = cluster.parser(extra_args)
    remote = local_host != cluster.host

    # Form call command
    if os.path.basename(args.executable) == 'python':
        ex = sys.executable
    else:
        ex = args.executable
    script_args_str = ' '.join(script_args)
    # Add memo_id to the command for easy tracking
    sep = ' -- ' if ' -- ' not in script_args_str else ' '
    command = f'{ex} {args.script} {script_args_str}{sep}--memo_id {cluster.memo_id}'

    # Prepare run.sh script
    script = cluster.gen_batch_script(command)

    # Define working dir where we will cd to
    if remote:
        working_dir = cluster.memo_dir
    else:
        if args.keep_cwd:
            working_dir = os.getcwd()
        else:
            working_dir = os.path.expandvars(cluster.memo_dir)

    # Define what to store in meta.json
    rec = {'start time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
           'full_command': ' '.join(sys.argv),
           'local host': local_host,
           'working dir': os.path.abspath(os.getcwd()),
           'remote host': cluster.host,
           'user': cluster.user,
           'cluster args': getattr(cluster.args, '__dict__', None),
           'script args': script_args,
           'outcome': '',
           'show': True,
           'memo_id': cluster.memo_id}
    rec.update(args.__dict__)

    # Copy everything to memo_dir
    login = f'{cluster.user}@{cluster.host}'
    if not args.dry:
        if remote:
            local_memo_dir = tempfile.mkdtemp()
        else:
            local_memo_dir = cluster.memo_dir
        print(local_memo_dir)

        # with tempfile.TemporaryDirectory() as dirname:
        shutil.copy2(sys.argv[2], local_memo_dir)
        with open(os.path.join(cluster.memo_dir, 'run.sh'), 'w') as f:
            f.write('\n'.join(script))
        meta_file = open(os.path.join(local_memo_dir, 'meta.json'), 'w')
        json.dump(rec, meta_file, indent=4)

        if remote:
            copy_files = ['rsync', '-aq',
                          os.path.join(local_memo_dir, '*'),
                          f'{login}:{local_memo_dir}']
            out = subprocess.run(' '.join(copy_files), shell=True, check=True)

    # Call run.sh
    call_args = [cluster.executor, 'run.sh']

    if remote:
        bash_cmd = f'cd {working_dir}; ' + ' '.join(call_args)
        if not args.dry:
            out = cluster.exec_remote(bash_cmd)
            if args.cluster == 'om':  # print job id
                print(out.rstrip('\n'))

    else:
        local_memo_dir = os.path.expandvars(local_memo_dir)

        if not args.follow:
            logfile = os.path.join(local_memo_dir, 'log.out')
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


CLUSTERS = {'local': Local,
            'braintree': BrainTree,
            'om': OpenMind,
            'vsc': VSC}

IPS = {
    '18.93.6.23': ('braintree-cpu-1.mit.edu', 'braintree'),
    '18.93.6.11': ('braintree-gpu-1.mit.edu', 'braintree'),
    '18.93.6.12': ('braintree-gpu-2.mit.edu', 'braintree'),
    '18.93.5.253': ('braintree-gpu-3.mit.edu', 'braintree'),
    '18.93.6.27': ('braintree-gpu-4.mit.edu', 'braintree'),
    '18.13.53.52': ('openmind7.mit.edu', 'om'),
    '10.118.230.3': ('login1-tier2.hpc.kuleuven.be', 'vsc')
}


if __name__ == '__main__':
    # watch_and_sync('/tmp/tmp3ai6985k')
    if 'on_exit' in sys.argv:
        idx = sys.argv.index('on_exit')
        on_exit(sys.argv[idx + 1])
    elif 'watch_and_sync' in sys.argv:
        idx = sys.argv.index('watch_and_sync')
        watch_and_sync(sys.argv[idx + 1])
    else:
        main()
