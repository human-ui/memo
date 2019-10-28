# Track your projects

Run a command with a `memo` prefix and that particular file along with its outputs gets saved to a folder. You can track progress easily within your browser by starting `server.py` and opening `http://localhost:5000/` in your browser.

Current limitation: only the file you execute gets saved. Thus, if your file has external dependencies, they must be specified with absolute paths and, unfortunately, they won't get saved.


## Setup

No dependencies outside the standard Python 3 libraries.

The database (which is just a plain folder) is expected to be on `braintree.mit.edu` but can be modified freely in the config file.

### Environment variables

You need to create a new environment variable `MEMO` that points to a folder where you will store your runs.

### Config

Create a config file in your home folder (`~/.memo`) with the following structure:

```
[db]
user = ...
host = braintree.mit.edu

[braintree]
user = ...

[om]
user = ...
qos = dicarlo
```

### Installation steps

#### Clone

```
git clone https://github.com/human-ui/memo.git ~/memo
```

#### Create DB directory

```
mkdir /data/memo-store
mkdir /data/memo-store/trash
```

#### Set env `MEMO`

```
echo export MEMO="$HOME/memo-store" >> .profile
```

#### Add `memo` bin to path

```
mkdir ~/bin
ln -s ~/memo/memo.py ~/bin/memo
```

#### Create config file

Minimal `~/.memo` config file pointing to localhost:
```
cat << EOT > ~/.memo
[db]
user = $USER
host = localhost
EOT
```

#### Allow ssh localhost without password

```
cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
```


## Usage

`memo <your command as usual>`

e.g.:

`memo python run.py value1 --arg2 value2`

Usually, you want to run it a couple of reserved memo arguments, such as `-d` (description).

In theory, you should be able to run your command on your local machine but specify that it should actually be executed on a remote server (e.g., `--cluster braintree --node gpu3`). I haven't tested it too much yet though.