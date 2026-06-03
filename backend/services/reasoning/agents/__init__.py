"""6대 섹터 에이전트 + 종합 에이전트 등록."""
from .maritime_agent    import MaritimeAgent
from .energy_agent      import EnergyAgent
from .techno_agent      import TechnoAgent
from .indo_pacific_agent import IndoPacificAgent
from .gray_zone_agent   import GrayZoneAgent
from .cyber_agent       import CyberAgent
from .synthesizer       import synthesize

ALL_AGENTS = [
    MaritimeAgent(),
    EnergyAgent(),
    TechnoAgent(),
    IndoPacificAgent(),
    GrayZoneAgent(),
    CyberAgent(),
]

__all__ = [
    "ALL_AGENTS",
    "synthesize",
    "MaritimeAgent",
    "EnergyAgent",
    "TechnoAgent",
    "IndoPacificAgent",
    "GrayZoneAgent",
    "CyberAgent",
]
