from invoke import task
from lexic.version import __version__

@task
def pypi(c):
    ver = __version__
    c.run('python setup.py bdist_wheel')
    c.run(f'python -m twine upload dist/lexic-{ver}-py3-none-any.whl')
    c.run(f'git commit -am "Committing everything for release {ver}"')
    c.run(f'git tag -a v{ver} -m "Tagging release {ver}"')
    c.run(f'git push')
    c.run(f'git push --tags')

@task
def tests(c):
    test_dir = 'test'
    c.run('pytest')
    c.run('pytest --cov-config .coveragerc --cov=lexic --cov-report=term --cov-report=html')
    c.run('coveralls')


@task
def docs(c):
    githubpages = "/Users/virantha/dev/githubdocs/lexic"
    with c.cd(githubpages):
        c.run('git checkout gh-pages')
        c.run('git pull origin gh-pages')
    #c.run("head CHANGES.rst > CHANGES_RECENT.rst")
    #c.run("tail -n 1 CHANGES.rst >> CHANGES_RECENT.rst")
    with c.cd("docs"):
        print("Running sphinx in docs/ and building to ~/dev/githubpages/lexic")
        c.run("make clean")
        c.run('rm -rf _auto_summary')
        c.run("make html")
        #c.run("cp -R ../test/htmlcov %s/html/testing" % githubpages)
    with c.cd(githubpages):
        #c.run("mv html/* .")
        c.run("git add .")
        c.run('git commit -am "doc update"')
        c.run('git push origin gh-pages')
