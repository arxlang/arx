# Installing ASTx

## Published package

```bash
pip install astx
```

ASTx supports Python 3.10 or newer.

For console ASCII rendering through `mermaid-ascii`:

```bash
pip install 'astx[console]'
```

The `all` extra currently installs the same optional visualization dependency:

```bash
pip install 'astx[all]'
```

Without the optional console dependency, console rendering falls back to YAML.

## Source checkout

ASTx is developed in the Arx monorepo:

```bash
git clone https://github.com/arxlang/arx.git
cd arx
mamba env create --file conda/dev.yaml
conda activate arx
poetry install
makim astx.unittests
```

The root Poetry project installs `packages/astx` as an editable dependency.
