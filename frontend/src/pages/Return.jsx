import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useLanguage } from "../contexts/LanguageContext";
import { useDarkMode } from "../contexts/DarkModeContext";
import {
  CreditCard,
  Package,
  CheckCircle,
  AlertCircle,
  ArrowLeft,
  Search,
} from "lucide-react";
import { getBorrows, returnItem, confirmReturn, openFreeLocker } from "../utils/api";

const Return = () => {
  const { user } = useAuth();
  const { t } = useLanguage();
  const { isDarkMode } = useDarkMode();
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [userId, setUserId] = useState("");
  const [borrowedItems, setBorrowedItems] = useState([]);
  const [selectedItem, setSelectedItem] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [itemSearchTerm, setItemSearchTerm] = useState("");
  const [selectedCondition, setSelectedCondition] = useState("");
  const [openedLockerId, setOpenedLockerId] = useState(null);



  const handleRfidScan = () => {
    // Simulate RFID scan for UX flow, but use authenticated user
    fetchBorrowedItems();
    setStep(2);
  };

  const handleUserIdSubmit = () => {
    if (userId.trim()) {
      fetchBorrowedItems();
      setStep(2);
    }
  };

  const fetchBorrowedItems = async () => {
    setLoading(true);
    setError("");
    try {
      console.log("Fetching borrowed items for user:", user.id);

      // Use API filtering instead of frontend filtering for better performance
      const response = await getBorrows({
        user_id: user.id,
        status: "borrowed",
        per_page: 100, // Get more items to avoid pagination issues
      });

      console.log("API response:", response);
      console.log("Borrowed items found:", response.borrows?.length || 0);

      setBorrowedItems(response.borrows || []);
    } catch (error) {
      console.error("Error fetching borrowed items:", error);
      setError(t("error_fetching_items"));
    } finally {
      setLoading(false);
    }
  };

  const handleItemSelect = (item) => {
    setSelectedItem(item);
    setStep(3);
  };

  const handleOpenFreeLocker = async () => {
    setLoading(true);
    setError("");
    setSuccess("");

    try {
      // call API to open a free locker
      const resp = await openFreeLocker();
      // resp must return { locker_id: number, message: string }
      setOpenedLockerId(resp.locker_id);
      setSuccess(`${t("locker_opened_for_return")} (#${resp.locker_id})`);
      setStep(5); // Now we will confirm the return
    } catch (err) {
      console.error("Error opening free locker:", err);
      setError(err.response?.data?.message || t("no_free_locker"));
    } finally {
      setLoading(false);
    }
  };

 const handleConfirmReturn = async () => {
  setLoading(true);
  setError("");
  setSuccess("");

  try {
    if (!selectedItem) {
      setError("no item selected.");
      setLoading(false);
      return;
    }

    if (!selectedCondition) {
      setError("Please select the item condition.");
      setLoading(false);
      return;
    }

    const payload = {
      user_id: user.id,
      item_id: selectedItem.id,
      condition: selectedCondition,
    };

    console.log("Payload retour →", payload);

    await confirmReturn(payload);

    setSuccess("Return confirmed!");
    setTimeout(() => navigate("/"), 1500);
  } catch (error) {
    console.error("Error confirming return:", error);
    setError(error.response?.data?.error || "Error during return.");
  } finally {
    setLoading(false);
  }
};

  const resetProcess = () => {
    setStep(1);
    setUserId("");
    setSelectedItem(null);
    setError("");
    setSuccess("");
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1
          className={`text-3xl font-bold mb-2 ${
            isDarkMode ? "text-white" : "text-gray-900"
          }`}
        >
          {t("return_item")}
        </h1>
        <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>
          {t("follow_steps_return")}
        </p>
      </div>

      {/* Progress Steps */}
      <div className="mb-8">
        <div className="flex items-center justify-center space-x-4">
          {[1, 2, 3, 4, 5].map((stepNumber) => (
            <div key={stepNumber} className="flex items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                  step >= stepNumber
                    ? "bg-primary-600 text-white"
                    : "bg-gray-200 text-gray-600"
                }`}
              >
                {stepNumber}
              </div>
              {stepNumber < 5 && (
                <div
                  className={`w-16 h-1 mx-2 ${
                    step > stepNumber ? "bg-primary-600" : "bg-gray-200"
                  }`}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Error/Success Messages */}
      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center">
          <AlertCircle className="h-5 w-5 mr-2" />
          {error}
        </div>
      )}

      {success && (
        <div className="mb-6 bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg flex items-center">
          <CheckCircle className="h-5 w-5 mr-2" />
          {success}
        </div>
      )}

      {/* Step 1: Authentication */}
      {step === 1 && (
        <div className="card text-center">
          <div className="mb-6">
            <div className="bg-primary-100 p-4 rounded-full w-20 h-20 mx-auto mb-4 flex items-center justify-center">
              <CreditCard className="h-10 w-10 text-primary-600" />
            </div>
            <h2
              className={`text-2xl font-semibold mb-2 ${
                isDarkMode ? "text-white" : "text-gray-900"
              }`}
            >
              {t("authentication")}
            </h2>
            <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>
              {t("choose_authentication_method")}
            </p>
          </div>

          {/* RFID Option */}
          <div className="mb-6">
            <div
              className={`p-4 rounded-lg mb-4 ${
                isDarkMode ? "bg-gray-700" : "bg-gray-50"
              }`}
            >
              <h3
                className={`text-lg font-medium mb-2 ${
                  isDarkMode ? "text-white" : "text-gray-900"
                }`}
              >
                {t("rfid_card")}
              </h3>
              <p
                className={`text-sm ${
                  isDarkMode ? "text-gray-300" : "text-gray-600"
                }`}
              >
                {t("scan_rfid_return_description")}
              </p>
              <button onClick={handleRfidScan} className="btn-primary mt-3">
                {t("simulate_rfid_scan")}
              </button>
            </div>

            {/* User ID Option */}
            <div
              className={`p-4 rounded-lg ${
                isDarkMode ? "bg-gray-700" : "bg-gray-50"
              }`}
            >
              <h3
                className={`text-lg font-medium mb-2 ${
                  isDarkMode ? "text-white" : "text-gray-900"
                }`}
              >
                {t("user_id")}
              </h3>
              <p
                className={`text-sm ${
                  isDarkMode ? "text-gray-300" : "text-gray-600"
                }`}
              >
                {t("enter_user_id_return_description")}
              </p>
              <div className="mt-3 flex space-x-2">
                <input
                  type="text"
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                  placeholder={t("enter_user_id")}
                  autoComplete="off"
                  inputMode="text"
                  enterKeyHint="done"
                  className={`flex-1 px-3 py-2 border rounded-md touch-manipulation ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                />
                <button
                  onClick={handleUserIdSubmit}
                  disabled={!userId.trim()}
                  className="btn-primary disabled:opacity-50"
                >
                  {t("continue")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Step 2: Item Selection */}
      {step === 2 && (
        <div className="card">
          <div className="mb-6">
            <h2
              className={`text-2xl font-semibold mb-2 ${
                isDarkMode ? "text-white" : "text-gray-900"
              }`}
            >
              {t("select_item_return")}
            </h2>
            <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>
              {t("choose_item_return")}
            </p>
          </div>

          {/* Search Input */}
          {borrowedItems.length > 0 && (
            <div className="mb-6">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
                <input
                  type="text"
                  placeholder={t("search_borrowed_items")}
                  value={itemSearchTerm}
                  onChange={(e) => setItemSearchTerm(e.target.value)}
                  autoComplete="off"
                  inputMode="text"
                  enterKeyHint="search"
                  className={`w-full pl-10 pr-4 py-2 border rounded-lg touch-manipulation ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                      : "bg-white border-gray-300 text-gray-900 placeholder-gray-500"
                  }`}
                />
              </div>
            </div>
          )}
          {loading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto mb-4"></div>
              <p
                className={`${isDarkMode ? "text-gray-300" : "text-gray-600"}`}
              >
                {t("loading")}...
              </p>
            </div>
          ) : borrowedItems.length === 0 ? (
            <div
              className={`text-center py-8 ${
                isDarkMode ? "text-gray-400" : "text-gray-500"
              }`}
            >
              <Package className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium mb-2">
                {t("no_borrowed_items")}
              </p>
              <p className="text-sm">{t("no_borrowed_items_desc")}</p>
            </div>
          ) : (
            (() => {
              const filteredItems = borrowedItems.filter(
                (item) =>
                  (item.item_name || "")
                    .toLowerCase()
                    .includes(itemSearchTerm.toLowerCase()) ||
                  (item.locker_name || "")
                    .toLowerCase()
                    .includes(itemSearchTerm.toLowerCase())
              );

              return filteredItems.length === 0 && itemSearchTerm ? (
                <div
                  className={`text-center py-8 ${
                    isDarkMode ? "text-gray-400" : "text-gray-500"
                  }`}
                >
                  <Package className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-lg font-medium mb-2">
                    {t("no_items_found")}
                  </p>
                  <p className="text-sm">{t("try_different_search")}</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {filteredItems.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => handleItemSelect(item)}
                      className={`p-4 border rounded-lg transition-colors text-left ${
                        isDarkMode
                          ? "border-gray-600 hover:border-primary-400 hover:bg-gray-700"
                          : "border-gray-200 hover:border-primary-300 hover:bg-primary-50"
                      }`}
                    >
                      <div className="flex items-center space-x-3">
                        <Package className="h-6 w-6 text-primary-600" />
                        <div>
                          <h3
                            className={`font-medium ${
                              isDarkMode ? "text-white" : "text-gray-900"
                            }`}
                          >
                            {item.item_name}
                          </h3>
                          <p
                            className={`text-sm ${
                              isDarkMode ? "text-gray-300" : "text-gray-600"
                            }`}
                          >
                            {t("locker")} {item.locker_name}
                          </p>
                          <p
                            className={`text-xs ${
                              isDarkMode ? "text-gray-400" : "text-gray-500"
                            }`}
                          >
                            {t("borrowed_on")}:{" "}
                            {new Date(item.borrowed_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              );
            })()
          )}
        </div>
      )}

      {/* Step 3: Select item condition */}
      {step === 3 && (
        <div className="card text-center">
          <h2 className={`text-2xl font-semibold mb-2 ${isDarkMode ? "text-white" : "text-gray-900"}`}>
            {t("confirm_equipment_presence")}
          </h2>
          <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"} mb-6`}>
            {t("please_confirm_equipment_return")}
          </p>

          <div className="flex justify-center space-x-4">
            <button onClick={() => { setSelectedCondition("good"); setStep(4); }} className="btn-secondary">
              {t("equipment_good")}
            </button>
            <button onClick={() => { setSelectedCondition("damaged"); setStep(4); }} className="btn-secondary">
              {t("equipment_damaged")}
            </button>
          </div>
        </div>
      )}     
      {/* Step 4: Open free locker */}
      {step === 4 && (
        <div className="card text-center">
          <h2 className={`text-2xl font-semibold mb-2 ${isDarkMode ? "text-white" : "text-gray-900"}`}>
            {t("open_free_locker")}
          </h2>
          <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"} mb-6`}>
            {t("system_will_open_free_locker")}
          </p>

          <div className="flex space-x-4 justify-center">
            <button onClick={resetProcess} className="btn-secondary">
              {t("cancel")}
            </button>
            <button
              onClick={handleOpenFreeLocker}
              disabled={loading}
              className="btn-primary"
            >
              {loading ? t("opening_locker") : t("open_locker_and_continue")}
            </button>
          </div>
        </div>
      )}
      {step === 5 && (
        <div className="card text-center">
          <h2 className={`text-2xl font-semibold mb-2 ${isDarkMode ? "text-white" : "text-gray-900"}`}>
            {t("confirm_equipment_return")}
          </h2>
          <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"} mb-6`}>
            {t("please_confirm_equipment_return_in_locker", { locker: openedLockerId })}
          </p>

          <div className="flex justify-center space-x-4">
            <button onClick={resetProcess} className="btn-secondary">
              {t("cancel")}
            </button>
            <button onClick={handleConfirmReturn} disabled={loading} className="btn-primary">
              {loading ? t("saving") : t("confirm_return")}
            </button>
          </div>
        </div>
      )}
      {/* Back Button */}
      <div className="mt-8 text-center">
        <button
          onClick={() => navigate("/")}
          className={`inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium ${
            isDarkMode
              ? "bg-gray-700 text-white hover:bg-gray-600 border-gray-600"
              : "bg-white text-gray-700 hover:bg-gray-50"
          }`}
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          {t("back_to_main_menu")}
        </button>
      </div>
    </div>
  );
};

export default Return;
