import axios from "axios";
import { useQuery } from "@tanstack/react-query";

const useStockfishEvaluation = (fen) => {
  const fetchWithTimeout = (url, options, timeout = 10000) => {
    return Promise.race([
      axios.get(url, options),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("Request timed out")), timeout)
      ),
    ]);
  };

  const fetchV2 = async (fen) => {
    const response = await fetchWithTimeout(
      "https://stockfish.online/api/s/v2.php",
      {
        params: {
          fen: fen,
          depth: 15,
        },
      }
    );

    if (response.data && response.data.success) {
      return {
        evaluation: response.data.evaluation,
        mate: response.data.mate,
        bestMove: response.data.bestmove.split(" ")[1],
        continuation: response.data.continuation,
      };
    } else {
      throw new Error("Error getting evaluation from v2 API");
    }
  };

  const fetchV1 = async (fen) => {
    const evalResponse = await axios.get(
      "https://stockfish.online/api/stockfish.php",
      {
        params: {
          fen: fen,
          depth: 15,
          mode: "eval",
        },
      }
    );

    const bestMoveResponse = await axios.get(
      "https://stockfish.online/api/stockfish.php",
      {
        params: {
          fen: fen,
          depth: 15,
          mode: "bestmove",
        },
      }
    );

    if (evalResponse.data.success && bestMoveResponse.data.success) {
      return {
        evaluation: parseFloat(evalResponse.data.data),
        mate: null, // v1 API doesn't provide mate information
        bestMove: bestMoveResponse.data.data.split(" ")[1],
        continuation: null, // v1 API doesn't provide continuation
      };
    } else {
      throw new Error("Error getting evaluation from v1 API");
    }
  };

  const fetchChessApi = async (fen) => {
    const response = await axios.post(
      "https://chess-api.com/v1",
      {
        fen: fen,
        depth: 12,
      },
      {
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    if (response.data) {
      return {
        evaluation: response.data.eval,
        mate: response.data.mate,
        bestMove: response.data.move,
        continuation: response.data.continuationArr,
      };
    } else {
      throw new Error("Error getting evaluation from Chess API");
    }
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["stockfishEvaluation", fen],
    queryFn: async () => {
      try {
        return await fetchV2(fen);
      } catch (error) {
        console.warn("V2 API failed or timed out, falling back to V1:", error);
        try {
          return await fetchV1(fen);
        } catch (error) {
          console.warn("V1 API failed or timed out, falling back to Chess API:", error);
          return await fetchChessApi(fen);
        }
      }
    },
    enabled: !!fen,
  });

  return {
    data,
    isLoading,
    error,
  };
};

export default useStockfishEvaluation;
