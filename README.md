setup:
  1. ```git clone https://github.com/tommy-mor/freeplane-mover.git```
  2. ```cd freeplane-mover```
  3. ```chmod +x convert.p```
  4. ```(optional) ln -s "$(pwd -P)/convert.py" /usr/local/bin/freeplane-mover```

example workflow:
  1. create mindmap file that represents directory: ```./convert.py makemap temp.mm DIRECTORY\_YOU\_WANT\_TO\_MODIFY```
  2. run mind map viewer on that file ```freeplane temp.mm >/dev/null & ```
  3. move directories around using freeplane mouse interface. save (ctrl-s) in freeplane when done
  3. read mindmap file (now modified) back, process changes, check that modifications are desired ```./convert.py apply out.mm```
  4. find the same changes, but this time execute the commands ```./convert.py apply out.min | bash```
