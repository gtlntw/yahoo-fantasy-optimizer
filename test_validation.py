import logging
from src import optimizer
from src import il_manager

logging.basicConfig(level=logging.INFO)

def test_optimizer_starting_pitcher_default():
    print("--- Testing Optimizer Starting Pitcher Default ---")
    
    # Roster with a starting pitcher (is_starting_pitcher=True), 
    # a relief pitcher (no SP eligibility), 
    # and a non-starting SP (missing is_starting_pitcher field - should default to False now)
    
    roster = [
        {
            "player_id": 1,
            "name": "Starting Ace",
            "position_type": "P",
            "selected_position": "P",
            "eligible_positions": ["SP"],
            "status": "",
            "has_game": True,
            "is_starting_pitcher": True,
            "ai_rank": 1
        },
        {
            "player_id": 2,
            "name": "Elite Closer",
            "position_type": "P",
            "selected_position": "RP",
            "eligible_positions": ["RP"],
            "status": "",
            "has_game": True,
            # Relief pitchers don't have is_starting_pitcher, defaults to False.
            # But they are not SP eligible, so they go to primary group.
            "ai_rank": 2
        },
        {
            "player_id": 3,
            "name": "Non-Starting SP",
            "position_type": "P",
            "selected_position": "SP",
            "eligible_positions": ["SP"],
            "status": "",
            "has_game": True,
            # Missing is_starting_pitcher. Before our fix, this defaulted to True,
            # putting them in primary group. Now it defaults to False, putting them in secondary.
            "ai_rank": 3
        }
    ]
    
    # We mock the slots to only have 2 pitcher spots, so 1 player must be benched.
    optimizer.PITCHER_SLOTS = [
        {"slot": "P", "eligible": None},
        {"slot": "P", "eligible": None},
    ]
    optimizer.BATTER_SLOTS = []
    
    changes = optimizer.optimize_lineup(roster)
    
    # Non-Starting SP should be the one benched
    benched_players = [c["player_name"] for c in changes if c["to"] == "BN"]
    print(f"Benched Players: {benched_players}")
    
    assert "Non-Starting SP" in benched_players, "Non-starting SP should be benched!"
    assert "Starting Ace" not in benched_players, "Starting Ace should NOT be benched!"
    assert "Elite Closer" not in benched_players, "Closer should NOT be benched!"
    print("✅ Optimizer logic works correctly: Non-starting SPs are properly deprioritized.")

def test_il_manager_slot_inference_and_healthy_split():
    print("\n--- Testing IL Manager Logic ---")
    
    roster = [
        {
            "player_id": 1,
            "name": "Healthy Player on IL",
            "selected_position": "IL",
            "status": "" # Healthy
        },
        {
            "player_id": 2,
            "name": "Still Injured Player on IL",
            "selected_position": "IL",
            "status": "IL10" # Injured
        },
        {
            "player_id": 3,
            "name": "Newly Injured Player",
            "selected_position": "BN",
            "status": "IL15" # Injured, needs IL
        },
        {
            "player_id": 4,
            "name": "Another Newly Injured Player",
            "selected_position": "OF",
            "status": "IL60" # Injured, needs IL
        }
    ]
    
    # Total IL slots inferred: 2 used slots (player 1 & 2).
    # Player 1 activates, leaving 1 used slot (player 2).
    # So 1 slot available. Only Player 3 should move to IL.
    
    moves = il_manager.manage_il(None, roster, dry_run=True)
    
    activations = [m["player_name"] for m in moves if m["action"] == "activate"]
    to_ils = [m["player_name"] for m in moves if m["action"] == "to_il"]
    
    print(f"Activations: {activations}")
    print(f"To IL: {to_ils}")
    
    assert "Healthy Player on IL" in activations
    assert "Still Injured Player on IL" not in activations
    assert len(to_ils) == 2, "Should have 2 available IL slots (3 total, 1 occupied after activation)!"
    assert "Newly Injured Player" in to_ils
    
    # Ensure player_name key exists (was causing KeyError)
    for move in moves:
        assert "player_name" in move, "player_name key missing from move dict!"
        
    print("✅ IL Manager logic works correctly: Healthy players activated, dynamic slot count works, player_name key present.")

if __name__ == "__main__":
    test_optimizer_starting_pitcher_default()
    test_il_manager_slot_inference_and_healthy_split()
    print("\n🎉 All validation tests passed!")
