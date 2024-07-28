import React, { useState, useEffect } from "react";
import PuzzleBoard from "./components/PuzzleBoard";
import MoveHistory from "./components/MoveHistory";

import useChessStore from "./stores/useChessStore";
import { fetchPuzzle } from "./services/puzzleService";

const PuzzlePage = () => {
  const [puzzle, setPuzzle] = useState(null);
  const [isCorrect, setIsCorrect] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hintUsed, setHintUsed] = useState(false);
  const { makeMove, resetGame, loadFen } = useChessStore();

  const loadPuzzle = async () => {
    setIsLoading(true);
    try {
      const newPuzzle = await fetchPuzzle();
      setPuzzle(newPuzzle);
      resetGame();
      loadFen(newPuzzle.fen);
      setIsCorrect(null);
      setHintUsed(false);
    } catch (error) {
      console.error("Error loading puzzle:", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadPuzzle();
  }, []);

  const handleMove = (move) => {
    if (!puzzle) return false;

    const result = makeMove(move.from, move.to);
    if (!result) return false;

    const userMove = `${move.from}${move.to}`;
    if (userMove === puzzle.solution[0]) {
      // Correct move
      puzzle.solution.shift();
      if (puzzle.solution.length === 0) {
        setIsCorrect(true);
        setTimeout(() => {
          loadPuzzle();
        }, 2000);
      } else {
        // Make opponent's move automatically
        setTimeout(() => {
          const opponentMove = puzzle.solution.shift();
          makeMove(opponentMove.slice(0, 2), opponentMove.slice(2, 4));
        }, 500);
      }
    } else {
      setIsCorrect(false);
      setTimeout(() => {
        loadFen(puzzle.fen);
        setIsCorrect(null);
      }, 2000);
    }

    return true;
  };

  const handleHint = () => {
    setHintUsed(true);
  };

  return (
    <div className="container mx-auto">
      <div className="shadow border bg-white rounded w-full mb-4">
        <h1 className="text-2xl font-bold p-4">Chess Puzzle</h1>
      </div>
      <div className="flex flex-col lg:flex-row gap-4">
        <div className="lg:w-2/3">
          {isLoading ? (
            <div className="text-center">Loading puzzle...</div>
          ) : (
            <>
              <PuzzleBoard
                onMove={handleMove}
                puzzle={puzzle}
                onHint={handleHint}
              />
              {isCorrect !== null && (
                <div
                  className={`mt-4 p-4 rounded ${
                    isCorrect ? "bg-green-100" : "bg-red-100"
                  }`}
                >
                  {isCorrect
                    ? `Correct! ${
                        hintUsed ? "Hint was used. " : ""
                      }Loading next puzzle...`
                    : "Incorrect. Try again!"}
                </div>
              )}
            </>
          )}
          <button
            onClick={loadPuzzle}
            className="mt-4 bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
            disabled={isLoading}
          >
            {isLoading ? "Loading..." : "New Puzzle"}
          </button>
        </div>
        <div className="lg:w-1/3">
          <MoveHistory />
        </div>
      </div>
    </div>
  );
};

export default PuzzlePage;
