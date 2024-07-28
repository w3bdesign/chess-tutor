// services/puzzleService.js
import { Chess } from 'chess.js';

export const fetchPuzzle = async () => {
  try {
    const response = await fetch('https://lichess.org/api/puzzle/daily');
    const data = await response.json();
    
    // Create a new Chess instance
    const chess = new Chess();
    
    // Split the PGN string into individual moves
    const moves = data.game.pgn.split(' ');
    
    // Apply moves up to the puzzle's initial position
    for (let i = 0; i < data.puzzle.initialPly; i++) {
      const result = chess.move(moves[i]);
      if (!result) {
        throw new Error(`Invalid move: ${moves[i]}`);
      }
    }
    
    return {
      id: data.puzzle.id,
      fen: chess.fen(),  // Get the FEN of the puzzle's initial position
      solution: data.puzzle.solution,
      rating: data.puzzle.rating,
      themes: data.puzzle.themes,
    };
  } catch (error) {
    console.error('Error fetching puzzle:', error);
    throw error;
  }
};