import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useLanguage } from "../contexts/LanguageContext";
import { useDarkMode } from "../contexts/DarkModeContext";
import {
  CreditCard,
  Package,
  MapPin,
  CheckCircle,
  AlertCircle,
  ArrowLeft,
  Search,
} from "lucide-react";
import { getItems, getLockers, borrowItem, confirmPresence } from "../utils/api";

const Borrow = () => {
  const { user } = useAuth();
  const { t } = useLanguage();
  const { isDarkMode } = useDarkMode();
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [rfidCard, setRfidCard] = useState("");
  const [userId, setUserId] = useState("");
  const [useUserId, setUseUserId] = useState(false);
  const [selectedItem, setSelectedItem] = useState(null);
  const [selectedLocker, setSelectedLocker] = useState(null);
  const [items, setItems] = useState([]);
  const [lockers, setLockers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [itemSearchTerm, setItemSearchTerm] = useState("");
  const [lockerSearchTerm, setLockerSearchTerm] = useState("");

  useEffect(() => {
    fetchItems();
    fetchLockers();
  }, []);

  useEffect(() => {
   console.log("📄 Page Borrow chargée !");
  }, []);

  const fetchItems = async () => {
    try {
      const [itemsData, lockersData] = await Promise.all([
        getItems(),
        getLockers(),
      ]);

      // Filter items to only show those that are:
      // 1. Available (status = "available")
      // 2. In a locker (has locker_id)
      // 3. In an active locker (locker status = "active")
      const borrowableItems = itemsData.filter((item) => {
        if (item.status !== "available" || !item.locker_id) {
          return false;
        }

        const itemLocker = lockersData.find(
          (locker) => locker.id === item.locker_id
        );
        return itemLocker && itemLocker.status === "active";
      });

      setItems(borrowableItems);
    } catch (error) {
      console.error("Error fetching items:", error);
    }
  };

  const fetchLockers = async () => {
    try {
      const data = await getLockers();
      // Sort lockers: active first, then by status groups
      const sortedLockers = data.sort((a, b) => {
        // Active lockers first
        if (a.status === "active" && b.status !== "active") return -1;
        if (b.status === "active" && a.status !== "active") return 1;

        // Then sort by status alphabetically within groups
        if (a.status !== b.status) return a.status.localeCompare(b.status);

        // Finally sort by locker number
        return a.number.localeCompare(b.number);
      });
      setLockers(sortedLockers);
    } catch (error) {
      console.error("Error fetching lockers:", error);
    }
  };

  const handleRfidScan = () => {
    // Simulate RFID scan
    const mockRfid =
      "RFID_" + Math.random().toString(36).substr(2, 9).toUpperCase();
    setRfidCard(mockRfid);
    setUseUserId(false);
    setStep(2);
  };

  const handleUserIdSubmit = () => {
    if (userId.trim()) {
      setUseUserId(true);
      setStep(2);
    }
  };

  const handleItemSelect = (item) => {
    setSelectedItem(item);
    setStep(3);
  };

  const handleLockerSelect = (locker) => {
    setSelectedLocker(locker);
    setStep(4);
  };

  const handleConfirmBorrow = async () => {
    setLoading(true);
    setError("");
 
    try {
      await borrowItem({
        user_id: user.id,
        item_id: selectedItem.id,
        locker_id: selectedLocker.id,
      });

      setSuccess(t("borrow_success"));

      // Refresh data after successful borrow
      await fetchItems();
      await fetchLockers();

      setStep(5);
    } catch (error) {
      setError(error.response?.data?.message || t("borrow_error"));
    } finally {
      setLoading(false);
    }
  };

  const handleOpenLocker = async () => {
    setLoading(true);
    setError("");
    setSuccess("");

    try {
      // 🔓 1️⃣ Ouvre la porte via l’API Flask
      //const response = await api.post(`api/lockers/${selectedLocker.id}/open`);
      //console.log("✅ Casier ouvert :", response.data);
      await new Promise((r) => setTimeout(r, 1000));
      console.log("🔓 Simulation : ouverture casier réussie");

      // 2️⃣ Indique à l’utilisateur que la porte est ouverte
      setSuccess(t("locker_opened_wait_presence"));

      // 3️⃣ Passe à l’étape 5 (confirmation de présence)
      setStep(5);
    } catch (err) {
      console.error("Erreur ouverture casier :", err);
      setError(t("open_locker_error"));
    } finally {
      setLoading(false);
    }
  };

 const handleConfirmPresence = async (isPresent) => {
  setLoading(true);
  setError("");
  setSuccess("");

  console.log("✅ handleConfirmPresence called");
  console.log("User:", user);
  console.log("Selected item:", selectedItem);
  console.log("Selected locker:", selectedLocker);

  if (!selectedLocker || !selectedItem || !user) {
    setError("Informations manquantes pour confirmer la présence");
    setLoading(false);
    return;
  }

  try {
    // 1️⃣ Envoi de la confirmation de présence au backend
    const payload = {
      user_id: user.id,
      item_id: selectedItem.id,
      present: isPresent,
      message: isPresent ? "Borrow confirmed" : "Item missing",
    };

    console.log("Payload envoyé à /lockers/:id/confirm_presence :", payload);

    await confirmPresence(selectedLocker.id, payload);

    // 2️⃣ Gestion du résultat
    if (isPresent) {
      setSuccess(t("borrow_success_confirmed"));
    } else {
      setError(t("equipment_missing_reported"));
    }

    // 3️⃣ Rafraîchir l'état local
    await fetchItems();
    await fetchLockers();

    // 4️⃣ Retour au menu principal après un petit délai
    setTimeout(() => {
      navigate("/");
    }, 2000);
  } catch (err) {
    console.error("Erreur confirmation présence :", err);
    setError(t("borrow_error"));
  } finally {
    setLoading(false);
  }
};

  const resetProcess = () => {
    setStep(1);
    setRfidCard("");
    setSelectedItem(null);
    setSelectedLocker(null);
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
          {t("borrow_item")}
        </h1>
        <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>
          {t("follow_steps_borrow")}
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
                {t("scan_rfid_description")}
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
                {t("enter_user_id_description")}
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
              {t("select_item")}
            </h2>
            <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>
              {t("choose_item_borrow")}
            </p>
          </div>

          {/* Search Input */}
          <div className="mb-6">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                placeholder={t("search_items")}
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

          {(() => {
            const filteredItems = items.filter(
              (item) =>
                item.name
                  .toLowerCase()
                  .includes(itemSearchTerm.toLowerCase()) ||
                item.description
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
                          {item.name}
                        </h3>
                        <p
                          className={`text-sm ${
                            isDarkMode ? "text-gray-300" : "text-gray-600"
                          }`}
                        >
                          {item.description}
                        </p>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            );
          })()}
        </div>
      )}

      {/* Step 3: Locker Selection */}
      {step === 3 && (
        <div className="card">
          <div className="mb-6">
            <h2
              className={`text-2xl font-semibold mb-2 ${
                isDarkMode ? "text-white" : "text-gray-900"
              }`}
            >
              {t("select_locker")}
            </h2>
            <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>
              {t("select_available_locker")}
            </p>
          </div>

          {/* Search Input */}
          <div className="mb-6">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                placeholder={t("search_lockers")}
                value={lockerSearchTerm}
                onChange={(e) => setLockerSearchTerm(e.target.value)}
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

          {/* Locker with Selected Item */}
          {selectedItem && selectedItem.locker_id && (
            <div className="mb-8">
              <h3
                className={`text-lg font-medium mb-4 text-green-600 ${
                  isDarkMode ? "text-green-400" : "text-green-600"
                }`}
              >
                {t("locker_with_item")} (1)
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {lockers
                  .filter(
                    (locker) =>
                      locker.id === selectedItem.locker_id &&
                      locker.status === "active" &&
                      (locker.number
                        .toLowerCase()
                        .includes(lockerSearchTerm.toLowerCase()) ||
                        locker.location
                          .toLowerCase()
                          .includes(lockerSearchTerm.toLowerCase()))
                  )
                  .map((locker) => (
                    <button
                      key={locker.id}
                      onClick={() => handleLockerSelect(locker)}
                      className={`p-4 border-2 border-green-300 rounded-lg transition-colors text-left hover:border-green-500 hover:shadow-md ${
                        isDarkMode
                          ? "bg-green-900/20 hover:bg-green-800/30"
                          : "bg-green-50 hover:bg-green-100"
                      }`}
                    >
                      <div className="flex items-center space-x-3">
                        <MapPin className="h-6 w-6 text-green-600" />
                        <div>
                          <h3
                            className={`font-medium ${
                              isDarkMode ? "text-white" : "text-gray-900"
                            }`}
                          >
                            {t("locker")} {locker.number}
                          </h3>
                          <p
                            className={`text-sm ${
                              isDarkMode ? "text-gray-300" : "text-gray-600"
                            }`}
                          >
                            {locker.location}
                          </p>
                          <span className="inline-block mt-1 px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded-full">
                            {t("contains_item")}
                          </span>
                        </div>
                      </div>
                    </button>
                  ))}
              </div>
            </div>
          )}

          {/* Empty Active Lockers Section */}
          {lockers.filter(
            (locker) =>
              locker.status === "active" &&
              locker.id !== selectedItem?.locker_id
          ).length > 0 && (
            <div className="mb-8">
              <h3
                className={`text-lg font-medium mb-4 ${
                  isDarkMode ? "text-gray-400" : "text-gray-600"
                }`}
              >
                {t("empty_lockers")} (
                {
                  lockers.filter(
                    (locker) =>
                      locker.status === "active" &&
                      locker.id !== selectedItem?.locker_id
                  ).length
                }
                )
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {lockers
                  .filter(
                    (locker) =>
                      locker.status === "active" &&
                      locker.id !== selectedItem?.locker_id &&
                      (locker.number
                        .toLowerCase()
                        .includes(lockerSearchTerm.toLowerCase()) ||
                        locker.location
                          .toLowerCase()
                          .includes(lockerSearchTerm.toLowerCase()))
                  )
                  .map((locker) => (
                    <div
                      key={locker.id}
                      className={`p-4 border rounded-lg text-left opacity-60 cursor-not-allowed border-gray-300 ${
                        isDarkMode ? "bg-gray-800/50" : "bg-gray-50"
                      }`}
                    >
                      <div className="flex items-center space-x-3">
                        <MapPin className="h-6 w-6 text-gray-500" />
                        <div>
                          <h3
                            className={`font-medium ${
                              isDarkMode ? "text-gray-300" : "text-gray-700"
                            }`}
                          >
                            {t("locker")} {locker.number}
                          </h3>
                          <p
                            className={`text-sm ${
                              isDarkMode ? "text-gray-400" : "text-gray-500"
                            }`}
                          >
                            {locker.location}
                          </p>
                          <span className="inline-block mt-1 px-2 py-1 text-xs font-medium bg-gray-100 text-gray-800 rounded-full">
                            {t("no_item")}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Unavailable Lockers Sections */}
          {["reserved", "maintenance", "inactive"].map((status) => {
            const statusLockers = lockers.filter(
              (locker) => locker.status === status
            );
            if (statusLockers.length === 0) return null;

            const statusColors = {
              reserved: {
                border: "border-yellow-300",
                bg: isDarkMode ? "bg-yellow-900/20" : "bg-yellow-50",
                icon: "text-yellow-600",
                badge: "bg-yellow-100 text-yellow-800",
                title: isDarkMode ? "text-yellow-400" : "text-yellow-600",
              },
              maintenance: {
                border: "border-orange-300",
                bg: isDarkMode ? "bg-orange-900/20" : "bg-orange-50",
                icon: "text-orange-600",
                badge: "bg-orange-100 text-orange-800",
                title: isDarkMode ? "text-orange-400" : "text-orange-600",
              },
              inactive: {
                border: "border-gray-300",
                bg: isDarkMode ? "bg-gray-800/50" : "bg-gray-50",
                icon: "text-gray-500",
                badge: "bg-gray-100 text-gray-800",
                title: isDarkMode ? "text-gray-400" : "text-gray-600",
              },
            };

            const colors = statusColors[status];

            return (
              <div key={status} className="mb-6">
                <h3 className={`text-lg font-medium mb-4 ${colors.title}`}>
                  {t(`${status}_lockers`)} ({statusLockers.length})
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {statusLockers
                    .filter(
                      (locker) =>
                        locker.number
                          .toLowerCase()
                          .includes(lockerSearchTerm.toLowerCase()) ||
                        locker.location
                          .toLowerCase()
                          .includes(lockerSearchTerm.toLowerCase())
                    )
                    .map((locker) => (
                      <div
                        key={locker.id}
                        className={`p-4 border rounded-lg text-left opacity-60 cursor-not-allowed ${colors.border} ${colors.bg}`}
                      >
                        <div className="flex items-center space-x-3">
                          <MapPin className={`h-6 w-6 ${colors.icon}`} />
                          <div>
                            <h3
                              className={`font-medium ${
                                isDarkMode ? "text-gray-300" : "text-gray-700"
                              }`}
                            >
                              {t("locker")} {locker.number}
                            </h3>
                            <p
                              className={`text-sm ${
                                isDarkMode ? "text-gray-400" : "text-gray-500"
                              }`}
                            >
                              {locker.location}
                            </p>
                            <span
                              className={`inline-block mt-1 px-2 py-1 text-xs font-medium rounded-full ${colors.badge}`}
                            >
                              {t(status)}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            );
          })}

          {/* No Available Lockers Message */}
          {selectedItem &&
            selectedItem.locker_id &&
            !lockers.find(
              (locker) =>
                locker.id === selectedItem.locker_id &&
                locker.status === "active"
            ) && (
              <div
                className={`text-center py-8 ${
                  isDarkMode ? "text-gray-400" : "text-gray-500"
                }`}
              >
                <MapPin className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p className="text-lg font-medium mb-2">
                  {t("item_locker_unavailable")}
                </p>
                <p className="text-sm">{t("item_locker_unavailable_desc")}</p>
              </div>
            )}

          {/* General No Lockers Message */}
          {lockers.length === 0 && (
            <div
              className={`text-center py-8 ${
                isDarkMode ? "text-gray-400" : "text-gray-500"
              }`}
            >
              <MapPin className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium mb-2">
                {t("no_available_lockers")}
              </p>
              <p className="text-sm">{t("all_lockers_occupied")}</p>
            </div>
          )}
        </div>
      )}

      {/* Step 4: Confirmation */}
      {step === 4 && (
        <div className="card">
          <div className="mb-6">
            <h2
              className={`text-2xl font-semibold mb-2 ${
                isDarkMode ? "text-white" : "text-gray-900"
              }`}
            >
              {t("confirm_borrow")}
            </h2>
            <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>
              {t("confirm_borrowing_details")}
            </p>
          </div>

          <div
            className={`rounded-lg p-6 mb-6 ${
              isDarkMode ? "bg-gray-700" : "bg-gray-50"
            }`}
          >
            <div className="space-y-4">
              <div className="flex justify-between">
                <span
                  className={`${
                    isDarkMode ? "text-gray-300" : "text-gray-600"
                  }`}
                >
                  {t("user")}:
                </span>
                <span
                  className={`font-medium ${
                    isDarkMode ? "text-white" : "text-gray-900"
                  }`}
                >
                  {user?.first_name} {user?.last_name} ({user?.username})
                </span>
              </div>
              <div className="flex justify-between">
                <span
                  className={`${
                    isDarkMode ? "text-gray-300" : "text-gray-600"
                  }`}
                >
                  {t("item")}:
                </span>
                <span
                  className={`font-medium ${
                    isDarkMode ? "text-white" : "text-gray-900"
                  }`}
                >
                  {selectedItem?.name}
                </span>
              </div>
              <div className="flex justify-between">
                <span
                  className={`${
                    isDarkMode ? "text-gray-300" : "text-gray-600"
                  }`}
                >
                  {t("locker")}:
                </span>
                <span
                  className={`font-medium ${
                    isDarkMode ? "text-white" : "text-gray-900"
                  }`}
                >
                  {t("locker")} {selectedLocker?.number}
                </span>
              </div>
            </div>
          </div>

          <div className="flex space-x-4">
            <button onClick={resetProcess} className="btn-secondary">
              {t("cancel")}
            </button>
            <button
              onClick={handleOpenLocker}
              disabled={loading}
              className="btn-primary flex-1"
            >
              {loading ? (
                t("opening_locker")
              ) : (
                t("open_locker_and_continue")
              )}
            </button>
          </div>
        </div>
      )}
     {step === 5 && (
        <div className="card text-center">
          <h2
            className={`text-2xl font-semibold mb-2 ${
              isDarkMode ? "text-white" : "text-gray-900"
            }`}
          >
            {t("confirm_equipment_presence")}
          </h2>
          <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"} mb-6`}>
            {t("please_confirm_equipment_inside")}
          </p>

          <div className="flex justify-center space-x-4">
            <button
              onClick={() => handleConfirmPresence(true)}
              disabled={loading}
              className="btn-secondary"
            >
              {t("equipment_present")}
            </button>
            <button
              onClick={() => handleConfirmPresence(false)}
              disabled={loading}
              className="btn-secondary"
            >
              {t("equipment_missing")}
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

export default Borrow;
