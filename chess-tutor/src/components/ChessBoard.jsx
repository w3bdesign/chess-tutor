import { useEffect, useRef, useState } from "react";
import { Chessboard2 } from "@chrisoakman/chessboard2/dist/chessboard2.min.mjs";
import { Chess } from "chess.js";

import useStockfishEvaluation from "../hooks/useStockfishEvaluation";

function ChessBoard({ setMovePairs }) {
  const chessboardRef = useRef(null);
  const chessRef = useRef(new Chess());
  const bestMoveArrowRef = useRef(null);

  const [moveHistory, setMoveHistory] = useState([]);
  const [warningMessage, setWarningMessage] = useState(null);

  const {
    data: evaluationData,
    isLoading,
    error,
  } = useStockfishEvaluation(chessRef.current.fen());

  useEffect(() => {
    const pairs = [];
    for (let i = 0; i < moveHistory.length; i += 2) {
      pairs.push({
        white: moveHistory[i],
        black: moveHistory[i + 1] || null,
      });
    }
    setMovePairs(pairs);
  }, [moveHistory, setMovePairs]);

  useEffect(() => {
    const boardConfig = {
      draggable: true,
      position: "start",
      showNotation: true,

      onDrop: ({ source, target }) => {
        try {
          const move = chessRef.current.move({
            from: source,
            to: target,
            promotion: "q",
          });

          if (move === null) {
            const piece = chessRef.current.get(source);
            if (!piece) {
              setWarningMessage("No piece at the starting square.");
            } else if (
              chessRef.current.get(target) &&
              piece.color === chessRef.current.get(target).color
            ) {
              setWarningMessage("Cannot capture your own piece.");
            } else {
              setWarningMessage(
                `Invalid move for ${piece.type}. Please try again.`
              );
            }
            return "snapback";
          }

          chessboardRef.current.position(chessRef.current.fen());
          setMoveHistory(chessRef.current.history({ verbose: true }));
          setWarningMessage(null);

          // Clear previous arrows
          chessboardRef.current.clearArrows();
          bestMoveArrowRef.current = null;
        } catch (error) {
          console.error("Error making move:", error);
          const errorMessage = error.message.includes("Invalid move")
            ? "This move is not allowed. Please try a different move."
            : "An unexpected error occurred. Please try again.";
          setWarningMessage(errorMessage);
          return "snapback";
        }
      },
    };

    chessboardRef.current = Chessboard2("myBoard", boardConfig);

    return () => {
      if (chessboardRef.current) {
        //chessboardRef.current.destroy();
      }
    };
  }, []);

  useEffect(() => {
    if (evaluationData && evaluationData.bestMove) {
      const from = evaluationData.bestMove.slice(0, 2);
      const to = evaluationData.bestMove.slice(2, 4);

      // Remove the previous best move arrow if it exists
      if (bestMoveArrowRef.current) {
        chessboardRef.current.removeArrow(bestMoveArrowRef.current);
      }

      // Add the new best move arrow
      bestMoveArrowRef.current = chessboardRef.current.addArrow({
        color: "#89736b",
        start: from,
        end: to,
        size: "medium",
        opacity: "60%",
      });
    }
  }, [evaluationData]);

  const formatEvaluation = (data) => {
    if (!data) return "";
    if (data.mate !== null) return `Mate in ${data.mate}`;
    return `Evaluation: ${data.evaluation.toFixed(2)}`;
  };

  return (
    <>
      <p className="text-lg p-4 mt-2 mb-4 font-semibold shadow border bg-white rounded w-full">
        {error ? error.message : formatEvaluation(evaluationData)}
        {isLoading && "Calculating ..."}
      </p>
      {warningMessage && (
        <p className="text-red-500 p-2 mb-2 font-semibold">{warningMessage}</p>
      )}
      <div
        id="myBoard"
        className="shadow border bg-white rounded p-4 w-full min-w-[40rem] min-h-[35rem]"
      ></div>
    </>
  );
}

export default ChessBoard;
