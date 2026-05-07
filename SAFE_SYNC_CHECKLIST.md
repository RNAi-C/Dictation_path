# Safe Sync Checklist

Rules for safely synchronizing this project between computers.
Review this before every `git push`.

---

## Before Starting Work (any computer)

- [ ] Run `git pull` FIRST before making any changes
- [ ] Confirm you are on the `main` branch: `git branch`
- [ ] Confirm the repo is clean: `git status`

---

## Before Every Commit

Run `git status` and verify the staged files contain NONE of the following:

### NEVER commit patient data
- [ ] No patient names, IDs, or identifiers
- [ ] No case numbers or accession numbers
- [ ] No hospital or clinic names tied to cases
- [ ] No `patient_data/` folder contents
- [ ] No `transcripts/` folder contents

### NEVER commit dictated audio
- [ ] No `.wav`, `.mp3`, `.mp4`, `.m4a`, `.ogg`, `.flac` files
- [ ] No `audio/` folder contents
- [ ] These are excluded by `.gitignore` but verify manually

### NEVER commit model weights
- [ ] No `.bin`, `.pt`, `.pth`, `.ckpt`, `.onnx`, `.safetensors` files
- [ ] No `models/` folder contents
- [ ] Model files are large (140 MB - 1.5 GB) and must never be in Git

### NEVER commit logs
- [ ] No `data/*.log` files
- [ ] No `logs/` folder contents
- [ ] Logs may contain transcription text with PHI

### NEVER commit secrets or credentials
- [ ] No API keys
- [ ] No passwords
- [ ] No `local_settings.yaml` or `credentials/` folder
- [ ] No `.env` files

### NEVER commit build output
- [ ] No `PathDictate_Portable/` folder (7 GB portable build)
- [ ] No `.zip`, `.exe`, `.dll` files
- [ ] No `checksums/SHA256SUMS.txt`

### NEVER commit the virtual environment
- [ ] No `venv/` folder
- [ ] Recreate on each computer with: `pip install -r requirements.lock.txt`

---

## Commit Message Guidelines

Use short, descriptive messages:

```
git commit -m "Add lymphoma terminology to dictionary"
git commit -m "Fix streaming transcription lock bug"
git commit -m "Update config.yaml CPU defaults"
git commit -m "Improve GUI contrast and font sizes"
```

Avoid vague messages like "fix" or "update" alone.

---

## After Committing

- [ ] Run `git push` before switching computers
- [ ] Confirm push succeeded (no error messages)

---

## On the Second Computer

- [ ] Run `git pull` BEFORE making any changes
- [ ] If you forgot to pull and have local changes, see Conflict Recovery below

---

## Conflict Recovery

If Git reports a merge conflict:

```powershell
# See which files conflict
git status

# Open the conflicting file — look for:
# <<<<<<< HEAD
# (your local version)
# =======
# (incoming version from GitHub)
# >>>>>>> origin/main

# Edit the file to keep the correct version, then:
git add <filename>
git commit -m "Resolve merge conflict in <filename>"
git push
```

**Safe rule:** For the terminology dictionary (`pathology_dictionary.json`),
keep ALL entries from BOTH versions when merging — never delete entries silently.

---

## Quick Reference Commands

```powershell
git status              # see what changed
git diff                # see exact changes
git log --oneline -10   # see last 10 commits
git pull                # get latest from GitHub
git add .               # stage all changes
git commit -m "msg"     # commit with message
git push                # send to GitHub
git branch              # confirm current branch
```

---

## Safety Rule

> This project is a pathology dictation assistant only.
> It transcribes and corrects dictated text.
> It never diagnoses, infers findings, or invents pathology content.
