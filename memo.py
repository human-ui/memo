#!/usr/bin/env python
import os, sys, argparse, configparser, datetime, getpass, json, shutil, glob, shlex
import socket, subprocess, tempfile, time, importlib

DATA_DIR = os.environ['MEMO']
CONFIG = configparser.ConfigParser()
CONFIG.read(os.path.expanduser('~/.memo'))

"""
Config structure:

[db]
user = ...
host = braintree.mit.edu

[braintree]
user = ...

[om]
user = ...
qos = dicarlo

[vsc]
user = ...
"""


def get_host_properties():
    """
    Get host, cluster name and node using IP addres

    From: https://stackoverflow.com/a/166589
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    host, cluster = IPS.get(ip, ('localhost', os.uname().nodename))
    s.close()
    if cluster == 'braintree':
        if 'gpu' in host:
            node_id = host.split(".")[0].split("-")[-1]
            node = f'gpu{node_id}'
        else:
            node = 'cpu'
    else:
        node = None
    return host, cluster, node


def get_local_output(command):
    output = subprocess.run(command, shell=True, check=True,
                          stdout=subprocess.PIPE).stdout
    output = output.decode().strip('\n')
    return output


def exec_remote(command, user, host, wait=True):
    """
    Execute a command on a remote server and return stdout output
    """
    bash_command = f"bash --login -c '{command}'"
    out = subprocess.run(['ssh', f'{user}@{host}', bash_command],
                          stderr=subprocess.STDOUT,
                          stdout=subprocess.PIPE)
    return out.stdout.decode('ascii')
            

def get_remote_env_var(varname, user, host):
    """
    Get an environment variable from a remote server
    """
    out = exec_remote(f'echo ${varname}', user, host)
    var = out.split('\n')[-2] 
    return var


def get_memo_id(local_memo_dir):
    rec = json.load(open(os.path.join(local_memo_dir, 'meta.json'), 'r'))
    return rec['memo_id']


def watch_and_sync(local_memo_dir, sleep=5):
    """
    Watches a folder and syncs it to db
    """
    db_memo = get_remote_env_var('MEMO', CONFIG['db']['user'], CONFIG['db']['host'])
    memo_id = get_memo_id(local_memo_dir)
    db_memo_dir = os.path.join(db_memo, memo_id)
    last_update = 0
    while True:
        time.sleep(5)
        done = False
        for dirpath, dirnames, filenames in os.walk(local_memo_dir):
            for filename in filenames:
                this_update = os.path.getmtime(os.path.join(dirpath, filename))
                if this_update > last_update:
                    last_update = this_update
                    sync(local_memo_dir, db_memo_dir)
                    done = True
                    break
            if done:
                break


def sync(src, dst):
    """
    Sync local source folder to a remote destination
    """
    subprocess.Popen(['rsync', '-aq', f'{src}/',
                      f"{CONFIG['db']['user']}@{CONFIG['db']['host']}:{dst}"]).wait()


def on_exit(local_memo_dir):
    """
    Appends end time stamp after the process is over and syncs to db
    """    
    meta_path = os.path.join(local_memo_dir, 'meta.json')
    try:
        rec = json.load(open(meta_path, 'r'))
    except:
        time.sleep(1)
        rec = json.load(open(meta_path, 'r'))
    rec['end_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    json.dump(rec, open(meta_path, 'w'), indent=4)

    db_memo = get_remote_env_var('MEMO', CONFIG['db']['user'], CONFIG['db']['host'])
    memo_id = get_memo_id(local_memo_dir)
    db_memo_dir = os.path.join(db_memo, memo_id)
    sync(local_memo_dir, db_memo_dir)
    shutil.rmtree(local_memo_dir)


class Local(object):

    cluster = 'localhost'
    host = 'localhost'
    executor = 'sh'

    def __init__(self, tmp_dir=None, no_record=False):
        self.no_record = no_record

        if self.cluster == 'localhost':
            self.user = getpass.getuser()
        else:
            self.user = CONFIG[self.cluster]['user']

        self.args = None

        # memo_idx = ''.join(random.SystemRandom().choice(string.ascii_lowercase) for _ in range(4))
        self.memo_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

        local_host = get_host_properties()[0]
        if local_host == self.host:
            self.memo_dir = tempfile.mkdtemp() + os.path.sep
        else:
            if tmp_dir is None:
                command = 'mktemp -d'
                # command = 'echo $(python -c "import tempfile; print(tempfile.mkdtemp())")'
            else:
                command = f'mktemp -d -p {tmp_dir}'
                # command = 'echo $(python -c "import tempfile; print(tempfile.mkdtemp(dir='
                        #   f"'{tmp_dir}'))"
                        #   '")'
            out = self.exec_remote(command) 
            self.memo_dir = out.split('\n')[-2] + os.path.sep
        print('memo id:', self.memo_id)
        self.project_path = os.path.abspath(os.getcwd())

    def parser(self, args):
        return args

    def gen_batch_script(self, command, working_dir, prefix=None):
        script = '#!/bin/sh'
        if prefix is not None:
            if not isinstance(prefix, (tuple, list)):
                script = [script, prefix]
            else:
                script = [script] + list(prefix)
        else:
            script = [script]
        script += ['',
                   f'cd {working_dir}',
                   f'export MEMO_DIR={self.memo_dir}',
                   f'export PROJECT_PATH={self.project_path}']
        if not self.no_record:
            script += [f'nohup memo watch_and_sync {self.memo_dir} -- '
                       f'--memo_id {self.memo_id} &']
        script += ['WATCH_PID=$!',
                   command,
                   'kill $WATCH_PID']
        if not self.no_record:
            script += [f'memo on_exit {self.memo_dir}']
        return script

    def exec_remote(self, command):
        return exec_remote(command, self.user, self.host)


class BrainTree(Local):

    cluster = 'braintree'
    executor = 'sh'

    def __init__(self, node='cpu', *args, **kwargs):
        if node.startswith('gpu'):
            num = node[-1]
            node = node[:-1]
        else:
            num = '1'
        self.host = f'braintree-{node}-{num}.mit.edu'
        super().__init__(*args, **kwargs)


class OpenMind(Local):

    cluster = 'om'
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

    def gen_batch_script(self, command, working_dir):
        prefix = []
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
            if k == 'qos':
                if v:
                    v = CONFIG['om']['qos']
                else:
                    skip = True
            elif k == 'jobname' and v is None:
                skip = True
            elif k == 'singularity':
                skip = True

            if not skip:
                prefix.append(f'#SBATCH {key}={v}')

        if self.args.singularity:
            command = (f'singularity exec --bind /braintree:/braintree '
                        f'--bind /home:/home --bind /om:/om --nv '
                        f'docker://nvidia/cuda:9.0-cudnn7-runtime-centos7 '
                        f'{command}')
        return super().gen_batch_script(command, working_dir, prefix=prefix)


class VSC(Local):

    cluster = 'vsc'
    host = 'login1-tier2.hpc.kuleuven.be'
    executor = 'qsub'

    def __init__(self, tmp_dir=None, *args, **kwargs):
        # /tmp is not shared in the cluster so we need a user-level folder
        user = CONFIG[self.cluster]['user']
        # cannot get VSC_SCRATCH using ssh, so need a different hacky method
        # tmp_dir = get_remote_env_var('VSC_SCRATCH', user, self.host)
        tmp_dir = f'/scratch/leuven/{user[3:6]}/{user}'
        super().__init__(tmp_dir=tmp_dir, *args, **kwargs)
 
    def parser(self, args):
        parser = argparse.ArgumentParser()
        parser.add_argument('--time', default='4:00:00:00')
        parser.add_argument('--nodes', default=1, type=int)
        parser.add_argument('--pmem', default=None) #'5gb'
        parser.add_argument('--pvmem', default=None)
        parser.add_argument('--gpus', default=1, type=int)
        # parser.add_argument('--qos', default='q72h')
        parser.add_argument('-N', '--job_name', default=None)
        parser.add_argument('-A', '--project_name', default=CONFIG['vsc']['project_name'])
        self.args, script_args = parser.parse_known_args(args)
        return script_args

    def gen_batch_script(self, command, working_dir):
        l_options = ['time', 'pmem', 'pvmem', 'qos']
        l_list = []
        pbs = []
        for k, v in self.args.__dict__.items():
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
                option = f'-A {v}'
            else:
                raise ValueError(f'Option {k} with value {v} not recognized.')

            if option is not None and v is not None:
                pbs.append(option)

        if gpus != 0 and gpus is not None:
            l_list += [f'nodes={nodes}:ppn={9 * gpus}:gpus={gpus}',
                       'partition=gpu']
        pbs.append('-l ' + ",".join(l_list))
        pbs.append(f'-o {self.memo_dir}/log.out')
        pbs.append(f'-e {self.memo_dir}/log.err')
        pbs = ' '.join(pbs)

        return super().gen_batch_script(command, working_dir,
                                        prefix=(f'#PBS {pbs}', f'cd {self.memo_dir}'))


class Enuui(Local):

    cluster = 'enuui'
    host = '10.43.201.11'
    executor = 'sh'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable')
    parser.add_argument('script')
    parser.add_argument('-t', '--tag', default='')
    parser.add_argument('-d', '--description', default='')
    parser.add_argument('--cluster', choices=list(CLUSTERS.keys()))
    parser.add_argument('--node', default='gpu3')
    parser.add_argument('--keep_cwd', action='store_true', default=False)
    parser.add_argument('--follow', action='store_true', default=False)
    parser.add_argument('--dry', action='store_true', default=False)
    parser.add_argument('--no_record', action='store_true', default=False,
                        help='Choose if you do not want to store any record in the'
                             'database. Useful for debugging.')

    args, extra_args = parser.parse_known_args()    
    local_host, cluster, node = get_host_properties()  
    if args.cluster is None:  # run where you currently are
        args.cluster = cluster
        args.node = node

    cluster = CLUSTERS.get(args.cluster, Local)
    if args.cluster == 'braintree':
        cluster = cluster(node=args.node, no_record=args.no_record)
    else:
        cluster = cluster(no_record=args.no_record)
    remote = local_host != cluster.host

    # Parse host-specific arguments
    script_args = cluster.parser(extra_args)

    # Form call command
    # if os.path.basename(args.executable) == 'python':
    #     ex = sys.executable
    # else:
    ex = args.executable
    script_args_str = ' '.join([shlex.quote(s) for s in script_args])

    # Add memo_id to the command for easy tracking
    sep = ' -- ' if ' -- ' not in script_args_str else ' '
    command = f'{ex} {args.script} {script_args_str}{sep}--memo_id {cluster.memo_id}'

    # get git details
    is_git_repo = get_local_output('git rev-parse --is-inside-work-tree')
    if is_git_repo == 'true':
        git_commit = get_local_output('git rev-parse HEAD')
        remote_url = get_local_output('git remote get-url origin')
        if 'github.com' in remote_url:
            if remote_url.startswith('git@github.com'):
                repo = remote_url.split(":")[1][:-4]  # strip .git
                remote_url = f'https://github.com/{repo}'
        else:
            remote_url = None
        copy_path = get_local_output('git rev-parse --show-toplevel')
    else:
        git_commit = None
        remote_url = None
        copy_path = os.listdir(os.getcwd())

    # Define working dir where we will cd to
    if remote:
        run_dir = cluster.memo_dir
    else:
        if args.keep_cwd:
            run_dir = os.getcwd()
        else:
            run_dir = os.path.expandvars(cluster.memo_dir)

    diff = os.path.relpath(os.getcwd(), copy_path)
    working_dir = os.path.join(run_dir, 'source', diff)

    # Prepare run.sh script
    script = cluster.gen_batch_script(command, working_dir)

    # Define what to store in meta.json
    rec = {'start time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
           'end time': None,
           'full command': ' '.join(sys.argv),
           'local host': local_host,
           'working dir': os.path.abspath(os.getcwd()),
           'remote host': cluster.host,
           'user': cluster.user,
           'cluster args': getattr(cluster.args, '__dict__', None),
           'script args': script_args,
           'outcome': '',
           'github url': remote_url,
           'git commit': git_commit,
           'show': True,
           'memo_id': cluster.memo_id,
           }
    rec.update(args.__dict__)    

    # Copy everything to memo_dir
    login = f'{cluster.user}@{cluster.host}'
    if not args.dry:
        if remote:  # need to set up a local folder first
            local_memo_dir = tempfile.mkdtemp()
        else:  # local folder is already available
            local_memo_dir = cluster.memo_dir
        print('Local memo dir:', local_memo_dir)
        shutil.copytree(copy_path, os.path.join(local_memo_dir, 'source'))
        
        with open(os.path.join(local_memo_dir, 'run.sh'), 'w') as f:
            f.write('\n'.join(script))
        with open(os.path.join(local_memo_dir, 'meta.json'), 'w') as meta_file:
            json.dump(rec, meta_file, indent=4)
        if remote:                 
            copy_files = ['rsync', '-aq',
                          f'{local_memo_dir}/',
                          f'{login}:{cluster.memo_dir}']
            print('Remote memo dir:', cluster.memo_dir)
            out = subprocess.run(' '.join(copy_files), shell=True, check=True)

    # Call run.sh
    call_args = [cluster.executor, 'run.sh']

    if remote:
        bash_cmd = f'cd {run_dir}; ' + ' '.join(call_args)
        if not args.dry:
            out = cluster.exec_remote(bash_cmd)        
            # if args.cluster == 'om':  # print job id
            print(out.rstrip('\n'))

    else:
        local_memo_dir = os.path.expandvars(local_memo_dir)

        if not args.follow:
            logfile = os.path.join(local_memo_dir, 'log.out')
            subprocess.Popen(['nohup'] + call_args, cwd=run_dir,
                             stdin=subprocess.DEVNULL,
                             stdout=open(logfile, 'a'),
                             stderr=open(logfile, 'a'))
            time.sleep(1)
            subprocess.Popen(['cat', logfile])
        else:
            p = subprocess.Popen(call_args, cwd=run_dir)
            try:
                p.wait()
            except KeyboardInterrupt:
                p.terminate()


CLUSTERS = {'local': Local,
            'braintree': BrainTree,
            'om': OpenMind,
            'vsc': VSC,
            'enuui': Enuui}

IPS = {
    '18.18.93.36': ('braintree-cpu-1.mit.edu', 'braintree'),
    '18.18.93.39': ('braintree-gpu-1.mit.edu', 'braintree'),
    '18.18.93.40': ('braintree-gpu-2.mit.edu', 'braintree'),
    '18.18.93.37': ('braintree-gpu-3.mit.edu', 'braintree'),
    '18.18.93.38': ('braintree-gpu-4.mit.edu', 'braintree'),
    '18.13.53.52': ('openmind7.mit.edu', 'om'),
    '10.118.230.3': ('login.hpc.kuleuven.be', 'vsc'),
    '10.43.201.11': ('10.43.201.11', 'enuui')
}


if __name__ == '__main__':
    if 'on_exit' in sys.argv:
        idx = sys.argv.index('on_exit')
        on_exit(sys.argv[idx + 1])
    elif 'watch_and_sync' in sys.argv:
        idx = sys.argv.index('watch_and_sync')
        watch_and_sync(sys.argv[idx + 1])
    else:
        main()
