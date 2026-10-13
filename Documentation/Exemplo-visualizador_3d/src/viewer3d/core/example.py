"""Built-in example: silicon in the diamond structure (shown when no file is given)."""

SI_DIAMOND_INPUT = """\
&CONTROL
  calculation = 'scf'
  prefix = 'si'
/
&SYSTEM
  ibrav = 2
  celldm(1) = 10.2
  nat = 2
  ntyp = 1
  ecutwfc = 20.0
/
ATOMIC_SPECIES
Si 28.086 Si.pz-vbc.UPF
ATOMIC_POSITIONS alat
Si 0.00 0.00 0.00
Si 0.25 0.25 0.25
K_POINTS automatic
4 4 4 1 1 1
"""
