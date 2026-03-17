"""Squad Dynamics system.

Manages player hierarchy, social groups, and morale contagion.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Optional
import random

from fm.db.models import Player, PlayerRelationship

class InfluenceLevel(Enum):
    TEAM_LEADER = 4
    HIGHLY_INFLUENTIAL = 3
    INFLUENTIAL = 2
    OTHER = 1

@dataclass
class SocialGroup:
    id: int
    name: str
    members: List[int] = field(default_factory=list) # player_ids
    average_morale: float = 65.0

class DynamicsManager:
    def __init__(self, session):
        self.session = session

    def calculate_hierarchy(self, club_id: int) -> Dict[int, InfluenceLevel]:
        """Determine player influence levels for a club."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        hierarchy = {}
        
        # Sort by points: tenure + age + overall + leadership
        # This is a simplified proxy for FM's deep hierarchy
        player_scores = []
        for p in players:
            score = (p.overall or 50) * 0.5
            score += (p.leadership or 50) * 0.3
            score += (p.age - 16) * 2.0
            # Tenure would be better, but we don't have it explicitly yet.
            player_scores.append((p.id, score))
        
        player_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Top 1-2 are Team Leaders
        for i, (pid, score) in enumerate(player_scores):
            if i < 2:
                level = InfluenceLevel.TEAM_LEADER
            elif i < 6:
                level = InfluenceLevel.HIGHLY_INFLUENTIAL
            elif i < 12:
                level = InfluenceLevel.INFLUENTIAL
            else:
                level = InfluenceLevel.OTHER
            hierarchy[pid] = level
            
        return hierarchy

    def form_social_groups(self, club_id: int) -> List[SocialGroup]:
        """Group players together based on nationality and age.
        
        Future expansion: use PlayerRelationship strength.
        """
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        groups = []
        
        # 1. Nationality Clusters
        nations = set(p.nationality for p in players if p.nationality)
        for i, nation in enumerate(nations):
            members = [p.id for p in players if p.nationality == nation]
            if len(members) >= 3: # Only form a group if 3+ players share it
                groups.append(SocialGroup(id=i, name=f"{nation} Clique", members=members))
                
        # 2. Age Bracket Clusters
        youths = [p.id for p in players if p.age < 21]
        if len(youths) >= 3:
            groups.append(SocialGroup(id=len(groups)+1, name="Young Bucks", members=youths))
            
        vets = [p.id for p in players if p.age >= 30]
        if len(vets) >= 3:
            groups.append(SocialGroup(id=len(groups)+1, name="Old Guard", members=vets))
            
        return groups

    def update_morale_contagion(self, club_id: int):
        """Spread morale changes with social group amplification."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        hierarchy = self.calculate_hierarchy(club_id)
        social_groups = self.form_social_groups(club_id)
        
        # Mapping for quick lookup
        player_map = {p.id: p for p in players}
        
        # Global core influence
        total_weight = 0.0
        weighted_morale_sum = 0.0
        influencers = []
        
        for p in players:
            inf_level = hierarchy.get(p.id, InfluenceLevel.OTHER)
            weight = 1.0 if inf_level == InfluenceLevel.TEAM_LEADER else (0.5 if inf_level == InfluenceLevel.HIGHLY_INFLUENTIAL else 0.0)
            if weight > 0:
                weighted_morale_sum += (p.morale or 65.0) * weight
                total_weight += weight
                influencers.append((p.id, p.morale or 65.0, weight))
        
        avg_influence_morale = weighted_morale_sum / total_weight if total_weight > 0 else 65.0
        
        # Base boost for everyone
        if avg_influence_morale > 80:
            base_boost = 1.5
        elif avg_influence_morale < 40:
            base_boost = -2.5
        else:
            base_boost = 0.0
            
        # Apply base boost + social group amplification
        for p in players:
            if hierarchy.get(p.id) == InfluenceLevel.TEAM_LEADER:
                continue # Leaders set the vibe, they don't catch it as easily?
                
            # Find which groups this player belongs to
            relevant_groups = [g for g in social_groups if p.id in g.members]
            
            # Check for "sad influencers" in their specific groups
            group_amplification = 0.0
            for group in relevant_groups:
                # Is there a Team Leader in this group?
                group_leaders = [inf for inf in influencers if inf[0] in group.members and inf[2] == 1.0]
                if group_leaders:
                    group_avg = sum(l[1] for l in group_leaders) / len(group_leaders)
                    if group_avg < 40:
                        group_amplification -= 1.5 # Extra despair from their own clique leader
                    elif group_avg > 80:
                        group_amplification += 1.0 # Extra confidence
            
            total_change = base_boost + group_amplification
            if total_change != 0:
                p.morale = max(0.0, min(100.0, (p.morale or 65.0) + total_change * random.uniform(0.7, 1.3)))
