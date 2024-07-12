import { useEffect, useRef } from "react";
import { Chessboard2 } from "@chrisoakman/chessboard2/dist/chessboard2.min.mjs";

import useChessStore from "../stores/useChessStore";
import useStockfishEvaluation from "../hooks/useStockfishEvaluation";

function ChessBoard() {
  const chessboardRef = useRef(null);
  const bestMoveArrowRef = useRef(null);

  const {
    chess,
    makeMove,
    warningMessage,
    evaluationData,
    isLoading,
    error,
    setEvaluationData,
    setIsLoading,
    setError,
  } = useChessStore();

  const {
    data,
    isLoading: evalIsLoading,
    error: evalError,
  } = useStockfishEvaluation(chess.fen());

  useEffect(() => {
    setEvaluationData(data);
    setIsLoading(evalIsLoading);
    setError(evalError);
  }, [
    data,
    evalIsLoading,
    evalError,
    setEvaluationData,
    setIsLoading,
    setError,
  ]);

  useEffect(() => {
    const boardConfig = {
      draggable: true,
      position: "start",
      showNotation: true,
      onDrop: ({ source, target }) => {
        const moveSuccessful = makeMove(source, target);
        if (!moveSuccessful) return "snapback";
        chessboardRef.current.position(chess.fen());
        // Clear previous arrows
        chessboardRef.current.clearArrows();
        bestMoveArrowRef.current = null;
      },
    };

    chessboardRef.current = Chessboard2("myBoard", boardConfig);

    return () => {
      if (chessboardRef.current) {
        //chessboardRef.current.destroy();
      }
    };
  }, [chess, makeMove]);

  useEffect(() => {
    if (evaluationData && evaluationData.bestMove) {
      const from = evaluationData.bestMove.slice(0, 2);
      const to = evaluationData.bestMove.slice(2, 4);

      if (bestMoveArrowRef.current) {
        chessboardRef.current.removeArrow(bestMoveArrowRef.current);
      }

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
