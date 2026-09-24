"""Thin naomigd adapter for the shared GameCore RetroArch generator."""
from backend.services.configgen.helpers import retroarch

EMU_ID = 'naomigd'
PORTS = 2

# Public generator/snapshot contract.
def extract(text):
    return retroarch.extract(text)

def replace(text, block):
    return retroarch.replace(text, block)

def generate(player_index, pad, opts):
    return retroarch.generate(EMU_ID, PORTS, player_index, pad, opts)

def release(player_index, opts, occupied=()):
    return retroarch.release(EMU_ID, PORTS, player_index, opts, occupied)
