#!/usr/bin/env zsh -i

# Auto-generated by Voodoo
# First-time script for project setup (DELETE ME AFTER RUNNING!)
# Now using python3.7

DOCS_DIR=~/dev/githubdocs

print Setting up your virtualenv

rmvirtualenv lexic
if [ $? -ne 0 ]; then
    print Removing old virtualenv failed
    exit -1
fi
unset PYTHONPATH && mkvirtualenv --python=python3.7 lexic
if [ $? -ne 0 ]; then
    print Making lexic Virtual env failed
    exit -1
fi

workon lexic
if [ $? -ne 0 ]; then
    print Could not switch to lexic
    exit -1
fi
print Working in virtualenv lexic


# Set up the pip packages
pip install pytest mock pytest-cov python-coveralls coverage sphinx tox restview schema docopt
#pip install sphinx restview
echo "cd ~/dev/lexic" >> ~/dev/envs/lexic/bin/postactivate
echo "unset PYTHONPATH" >> ~/dev/envs/lexic/bin/postactivate

# Start python develop
python setup.py develop

# Initialize the git repo
github_remote='git@github.com:virantha/lexic.git'
git init
git remote add origin $github_remote
git add .
git commit -am "Setting up new project lexic"

# Prompt if we want to push to remote git
read -q "REPLY?Create remote repository at $github_remote [y/N]?"
if [[  $REPLY == y ]]; then
    curl --data '{"name":"lexic", "description":""}' --user "virantha" https://api.github.com/user/repos
fi

read -q "REPLY?Push to remote repository $github_remote [y/N]?"
if [[  $REPLY == y ]]; then
    git push -u origin master
fi

print
# Create the docs repository
current_dir=`pwd`
read -q "REPLY?Create and push docs to $github_remote [y/N]?"
if [[  $REPLY == y ]]; then
    # Go to the docs build dir, and check out our repo
    cd $DOCS_DIR
    git clone https://github.com/virantha/lexic.git
    cd lexic
    git checkout --orphan gh-pages
    git rm -rf .

    cd $current_dir/docs
    pip install sphinx
    make html
    cd $DOCS_DIR
    cd lexic
    touch .nojekyll
    git add .
    git commit -m "docs"
    git push origin gh-pages

fi
