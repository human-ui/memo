#!/usr/bin/env python
import sys, os, shutil, argparse, subprocess, socket, datetime, json

DATA_DIR = '/braintree/data2/active/users/qbilius/memo'


def append_timestamp():
    rec = json.load(open(os.environ['MEMO_DIR'] + 'meta.json', 'r'))
    rec['end_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    json.dump(rec, open(os.environ['MEMO_DIR'] + 'meta.json', 'w'), indent=4)


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('executable')
    parser.add_argument('script')
    parser.add_argument('-t', '--tag', default='')
    parser.add_argument('-d', '--description', default='')
    parser.add_argument('--slurm', action='store_true', default=False)
    parser.add_argument('--switch_dir', action='store_true', default=True)
    args, script_args = parser.parse_known_args(args)

    if args.slurm:
        parser = argparse.ArgumentParser()
        parser.add_argument('-t', '--time', default='2-00:00:00')
        parser.add_argument('-n', '--ntasks', default=1, type=int)
        parser.add_argument('-c', '--cpus_per_task', default=5, type=int)
        parser.add_argument('--gres', default='gpu:GEFORCEGTX1080TI:1')  # titan-x, GEFORCEGTX1080TI
        parser.add_argument('--mem', default='40G')
        parser.add_argument('--qos', action='store_true', default=False)
        parser.add_argument('--job_name', default=None)

        slurm_kwargs, script_args = parser.parse_known_args(script_args)
        if slurm_kwargs.qos:
            slurm_kwargs.qos = 'dicarlo'
        else:
            delattr(slurm_kwargs, 'qos')

        if slurm_kwargs.job_name is None:
            delattr(slurm_kwargs, 'job_name')

    # memo_idx = ''.join(random.SystemRandom().choice(string.ascii_lowercase) for _ in range(4))
    memo_idx = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    os.environ['MEMO_DIR'] = os.path.join(DATA_DIR, memo_idx) + os.sep

    if not os.path.isdir(os.environ['MEMO_DIR']):
        os.makedirs(os.environ['MEMO_DIR'])
        print('memo id:', memo_idx)
    else:
        raise ValueError('{} already exists'.format(os.environ['MEMO_DIR']))

    shutil.copy2(sys.argv[2], os.environ['MEMO_DIR'])

    command = ' '.join(script_args)
    if args.slurm and os.path.basename(args.executable) == 'python':
        command = f'{sys.executable} {args.script} {command}'
    else:
        command = f'{args.executable} {args.script} {command}'

    if args.slurm:
        with open(os.environ['MEMO_DIR'] + 'run.sh', 'w') as f:
            f.write('#!/bin/sh\n')
            for k,v in slurm_kwargs.__dict__.items():
                key = k.replace('_', '-')
                key = f'-{key}' if len(key) == 1 else f'--{key}'
                skip = False
                if key == 'qos':
                    if v:
                        v = 'dicarlo'
                    else:
                        skip = True
                elif key == 'jobname' and v is None:
                    skip = True

                if not skip:
                    f.write(f'#SBATCH {key}={v}\n')

            f.write('\n')
            f.write(f"export MEMO_DIR={os.environ['MEMO_DIR']}\n")
            if args.executable == 'python':
                f.write(f'singularity exec --bind /braintree:/braintree '
                        f'--bind /home:/home --bind /om:/om --nv '
                        f'docker://nvidia/cuda:9.0-cudnn7-runtime-centos7 '
                        f'"{command}"\n')
            else:
                f.write(f'"{command}"\n')

            f.write('memo append_timestamp\n')

        call_args = ['ssh', 'openmind7.mit.edu', 'sbatch', os.environ['MEMO_DIR'] + 'run.sh']

    else:
        with open(os.environ['MEMO_DIR'] + 'run.sh', 'w') as f:
            f.write(f'{command}\n')
            f.write('memo append_timestamp\n')

        call_args = ['sh', os.environ['MEMO_DIR'] + 'run.sh']

    rec = {'start_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'args': script_args,
            'host': socket.gethostname(),
            'working dir': os.path.abspath(os.getcwd()),
            'tag': args.tag,
            'description': args.description,
            'outcome': '',
            'slurm': args.slurm,
            'switch_dir': args.switch_dir,
            'show': True}

    json.dump(rec, open(os.environ['MEMO_DIR'] + 'meta.json', 'w'), indent=4)

    # requests.post('http://localhost:5000/wait-for-changes',
    #               data={'data': db.loc[db.index[-1:]].drop('show', 1).to_html()})
    subprocess.Popen(['nohup'] + call_args,
                     stdin=open('/dev/null', 'w'),
                     stdout=open(os.environ['MEMO_DIR'] + 'log.out', 'a'),
                     stderr=open(os.environ['MEMO_DIR'] + 'log.out', 'a'))


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print('nothing to do')
    else:
        if sys.argv[1] == 'append_timestamp':
            append_timestamp()
        elif sys.argv[1] == 'smemo':
            main(sys.argv + ['--slurm'])
        else:
            main()