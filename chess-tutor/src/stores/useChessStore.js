import { create } from "zustand";
import { Chess } from "chess.js";

const useChessStore = create((set, get) => ({
  chess: new Chess(),
  moveHistory: [],
  warningMessage: null,
  evaluationData: null,
  isLoading: false,
  error: null,
  fen: "",
  pgn: "",

  makeMove: (from, to) => {
    const { chess } = get();
    try {
      const move = chess.move({ from, to, promotion: "q" });
      if (move === null) {
        set({ warningMessage: getWarningMessage(chess, from, to) });
        return false;
      }
      set({
        moveHistory: chess.history({ verbose: true }),
        warningMessage: null,
      });
      return true;
    } catch (error) {
      console.error("Error making move:", error);
      set({
        warningMessage: error.message.includes("Invalid move")
          ? "This move is not allowed. Please try a different move."
          : "An unexpected error occurred. Please try again.",
      });
      return false;
    }
  },

  setEvaluationData: (data) => set({ evaluationData: data }),
  setIsLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),

  setFen: (fen) => set({ fen }),
  setPgn: (pgn) => set({ pgn }),

  resetGame: () => {
    set({
      chess: new Chess(),
      moveHistory: [],
      warningMessage: null,
      evaluationData: null,
      isLoading: false,
      error: null,
      fen: "",
      pgn: "",
    });
  },
}));

function getWarningMessage(chess, from, to) {
  const piece = chess.get(from);
  const targetPiece = chess.get(to);

  if (!piece) return "No piece at the starting square.";
  if (targetPiece && piece.color === targetPiece.color)
    return "Cannot capture your own piece.";
  return `Invalid move for ${piece.type}. Please try again.`;
}

export default useChessStore;
